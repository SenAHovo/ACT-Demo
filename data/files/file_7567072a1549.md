# ACT (Agentic Commerce Trust Protocol) Overview

## Background

As AI agents become widely adopted in commercial scenarios, the demand for autonomous transactions between agents continues to grow. ACT (Agentic Commerce Trust Protocol) is a trusted transaction protocol for agents proposed by Alipay.

## Core Mechanisms

ACT defines four key domains for agent transactions:

1. **Delegation & Authorization Domain**: Users delegate agents to complete transactions through IAC (Intent Authorization Credential)
2. **Commercial Interaction Domain**: Buyer and seller agents discover services and negotiate via the A2A protocol
3. **Payment & Settlement Domain**: Implements conditional payments based on HTTP 402 and Payment Proof
4. **Trust & Attestation Domain**: The entire transaction process is recorded on-chain to ensure non-repudiation

## Typical Flow

User delegates buyer agent to procure services → Buyer discovers seller's Skill catalog → Negotiate price and terms → Create IAC authorization → PSP executes payment → Seller fulfills and delivers → Both parties attest and confirm.