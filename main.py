# -*- coding: utf-8 -*-
import anthropic
import os
import requests
import json
import re

NOTION_API_KEY = os.environ["NOTION_API_KEY"]
DATABASE_ID = os.environ["DATABASE_ID"]

url = 'https://api.notion.com/v1/pages'

headers = {
    'Notion-Version': '2022-06-28',
    'Authorization': 'Bearer ' + NOTION_API_KEY,
    'Content-Type': 'application/json',
}

# マークダウンのリンクをnotion上で有効にするためのjsonを作る関数。
def parse_markdown_links(text):
    regex = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
    parts = []
    last_end = 0

    for match in re.finditer(regex, text):
        start, end = match.span()
        if start > last_end:
            parts.append({"type": "text", "text": {"content": text[last_end:start]}})
        parts.append({
            "type": "text",
            "text": {
                "content": match.group(1),
                "link": {"url": match.group(2)}
            }
        })
        last_end = end

    if last_end < len(text):
        parts.append({"type": "text", "text": {"content": text[last_end:]}})

    return parts

# マークダウンをnotion上で有効にするためのjsonを作る関数。
def markdown_to_notion_blocks(text):
    lines = text.split("\n")
    blocks = []
    parent_stack = [(0, blocks)]  # (indent_level, parent_list)

    for line in lines:
        if not line.strip():
            continue

        indent_level = (len(line) - len(line.lstrip(' '))) // 4
        content = line.strip()

        if content.startswith("- "):
            block = {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": parse_markdown_links(content[2:])
                }
            }
        elif content.startswith("# "):
            block = {
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": content[2:]}}]
                }
            }
        elif content.startswith("## "):
            block = {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": content[3:]}}]
                }
            }
        elif content.startswith("### "):
            block = {
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": content[4:]}}]
                }
            }
        else:
            block = {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": parse_markdown_links(content)
                }
            }

        while indent_level < parent_stack[-1][0]:
            parent_stack.pop()

        if indent_level > parent_stack[-1][0]:
            parent = parent_stack[-1][1][-1]["bulleted_list_item"]
            if "children" not in parent:
                parent["children"] = []
            parent["children"].append(block)
            parent_stack.append((indent_level, parent["children"]))
        else:
            parent_stack[-1][1].append(block)

        parent_stack[-1] = (indent_level, parent_stack[-1][1])

    # 空の children を持つブロックから children フィールドを削除
    def remove_empty_children(block):
        if "children" in block:
            if not block["children"]:
                del block["children"]
            else:
                for child in block["children"]:
                    remove_empty_children(child)

    for block in blocks:
        remove_empty_children(block)

    return blocks

# notionのデータベースへ送信する関数。
def send_notion(title, content_block):
    json_data = {
        "parent": {
            "database_id": DATABASE_ID
        },
        "properties": {
            "料理名": {
                "title": [
                    {
                        "text": {
                            "content": title
                        }
                    }
                ]
            },
            "評価": {  # select タグのプロパティ
                "select": {
                    "name": "未作成"  # ここに選択肢の名前を指定
                }
            },
        },
        "children": content_block
    }

    response = requests.post(url, headers=headers, json=json_data)
    print(response.status_code, response.text)

def Claude_call(input_text):
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=2000,
        system="以下に示される料理の作り方を調べて教えて下さい。「https://cookpad.com/search/｛調べた料理の名前｝」、「https://www.kurashiru.com/search?query={調べた料理の名前}」、「https://www.kyounoryouri.jp/search/recipe?keyword={調べた料理の名前}」のリンクと、その他あれば参考リンクも下さい。回答はマークダウンで、用件のみで答えて下さい。マークダウン記法のネストは2段階まで使用できます。",
        messages=[
            {"role": "user", "content": input_text}
        ]
    )
    return [message.content[0].text][0]

if __name__ == '__main__':
    dish_name = input("作りたい料理名を入れてね：")
    message = Claude_call(dish_name)
    content = markdown_to_notion_blocks(message)
    send_notion(dish_name, content)
    print(json.dumps(content, indent=2, ensure_ascii=False))
