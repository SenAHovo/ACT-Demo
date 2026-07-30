# 流式输出故障排查与经验总结

## 问题描述

Web GUI 对话面板中，AI 回复不是逐字/逐 token 出现，而是一次性完整显示，与 CLI 中的流式输出观感完全不同。

用户在 Edge 浏览器中实际验证："直接就是恢复一整个内容，不是流式输出"。

## 排查历程（为什么修了这么久）

### 第一轮：怀疑后端 SSE 未正常工作

**猜测**：`chat_stream()` 中的异步生成器可能被阻塞，或者 LLM streaming 没有逐 token yield。

**排查**：用 `curl -N` 直接请求 SSE 端点，发现：
- `transfer-encoding: chunked` 正常
- 首个字节（`: ok` SSE 注释）几乎立即到达
- `connected` 事件、`thinking` 事件逐批到达

**结论**：后端 SSE 流式输出完全正常，问题在**前端**。

---

### 第二轮：怀疑浏览器 fetch API 缓冲

**猜测**：浏览器的 `fetch` 可能不会在收到少量数据时立即触发 `reader.read()`，或者中间代理（nginx/iframe）有缓冲。

**排查方向**：
- 尝试修改 `Content-Type` 为 `text/plain`（避免浏览器对 `text/event-stream` 的特殊行为）
- 尝试添加 `: ok\n\n` SSE 注释来强制刷新 HTTP 响应头
- 尝试添加 `connected` 事件防止浏览器过早断开
- 尝试在服务启动时预初始化 agent，避免首次请求因 DB 初始化延迟而超时
- 尝试添加 `X-Accel-Buffering: no` 头（后发现仅对 nginx 有效，本地无 nginx）

**结论**：这些尝试都是在对的方向上（网络层），但对这个问题无效。`curl` 验证了传输层没问题，浏览器 `fetch` 的 `ReadableStream` API 也不缓冲 — 它会立即返回每个 chunk。

---

### 第三轮：怀疑 JS 语法/闭包错误

**猜测**：`const`/`let`/`var` 变量作用域导致状态错乱，或 `thinkingEl` 引用丢失。

**排错过程**：
- 发现 `const thinkingEl` 在后续被赋值为 `null` → 修复为 `let`
- 发现 `yield _sse("connected", ...)` 被误加到 `chat()`（非生成器函数）中，导致 `SyntaxError` → 移除
- 验证闭包变量（`currentToolMsg`、`fullText`）在 SSE 回调中引用正确

**结论**：修复了真实存在的 JS 错误，但并非流式观感问题的**根因**。

---

### 第四轮（最终定位）：`requestAnimationFrame` 渲染批处理

**根因**：`scheduleRender()` 函数的设计存在根本性缺陷。

**错误实现**：

```javascript
function scheduleRender(fn) {
    renderQueue.push(fn);
    if (!rafId) {
        rafId = requestAnimationFrame(function() {
            rafId = null;
            var q = renderQueue;
            renderQueue = [];          // 清空整个队列
            for (var i = 0; i < q.length; i++) {
                q[i]();                // 所有回调在同一个 for 循环中执行
            }
            // ...
        });
    }
}
```

**问题机制**：

1. SSE 的数据到达是**批量**的 — 网络 chunk 可能含 5-50 个 `thinking` 事件
2. `processBuffer()` 在一次调用中解析出所有这些事件，依次调用 `handleSSE()` → `scheduleRender()`
3. 所有渲染回调被 push 到 `renderQueue`
4. `requestAnimationFrame` 触发时，用 `for` 循环一次性全部执行
5. DOM 更新虽然发生，但浏览器在**同一帧内**完成所有重排重绘，人眼看到的是"瞬间全出来"

**本质**：`requestAnimationFrame` 的回调在浏览器渲染帧之间执行，但一个渲染帧通常只要 16ms。在 16ms 内批量更新 50 次 DOM，浏览器只显示最终结果，中间状态被跳过。

---

### 正确修复

```javascript
function processRenderQueue() {
    if (renderQueue.length === 0) {
        rafId = null;
        return;
    }
    var fn = renderQueue.shift();      // 每次只取一个
    fn();                               // 执行一次 DOM 更新
    var c = document.getElementById('chat-messages');
    c.scrollTop = c.scrollHeight;
    rafId = requestAnimationFrame(processRenderQueue);  // 递归调度下一帧
}
```

**关键区别**：每个 SSE 事件在独立的 `requestAnimationFrame`（~16ms 间隔）中渲染，产生逐 token 出现的视觉效果。

---

## 根因总结

| 层面 | 是否有问题 | 说明 |
|------|-----------|------|
| 后端 SSE 流式输出 | 正常 | `curl -N` 验证首字节、chunk 均即时到达 |
| HTTP 传输层 | 正常 | `transfer-encoding: chunked`，无代理缓冲 |
| 浏览器 fetch ReadableStream | 正常 | `reader.read()` 在每个 chunk 到达时立即返回 |
| JS SSE 解析 | 正常 | `processBuffer` 正确分割 `\n\n` 提取 event/data |
| **JS DOM 渲染调度** | **根因** | `scheduleRender` 将所有事件在同一帧内批量渲染 |

## 经验教训

1. **先用底层工具验证**：`curl -N` 快速排除了传输层和后端问题，避免在前端代码中瞎改。
2. **理解浏览器的渲染管线**：`requestAnimationFrame` 的目的是做"每一帧的统一更新"（批量提交），而不是"创建视觉上的逐步效果"。如果目标是逐步渲染，应该让每个更新分散到不同帧。
3. **区分"数据流式到达"和"视觉流式渲染"**：SSE 数据确实流式到达，但 DOM 更新可以批处理掉帧间状态。人眼需要至少 ~16ms/帧的间隔才能感知到变化。
4. **不要混淆问题层级**：多次尝试修复网络层/传输层的问题（Content-Type、proxy buffering、connected 事件），这些虽然在某些场景有意义，但对这个特定问题不是根因。
