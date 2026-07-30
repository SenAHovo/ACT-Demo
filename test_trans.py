import asyncio
from shared.file_storage import save_file
from seller.skills.translation import run

md_content = '# ACT Protocol\nACT is a trust protocol for agent commerce.'
saved = save_file(
    filename='test_translation.md',
    content=md_content.encode('utf-8'),
    description='Test translation input',
    tags=['test'],
    source='system'
)
file_id = saved['file_id']
print(f'File ID: {file_id}')

result = run({'file_id': file_id, 'source_lang': 'zh', 'target_lang': 'en'})
print(f'Success: {result.get("success")}')
if result.get('success'):
    print(f'Output: {result.get("output_filename")}')
else:
    print(f'Error: {result.get("payload", {}).get("error")}')
