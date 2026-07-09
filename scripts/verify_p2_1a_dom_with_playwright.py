"""
P2-1A 真实浏览器 DOM 验证脚本

使用 Playwright 读取 /observations 页面的真实 DOM 文本
"""

import sys
import os
import asyncio
import json

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


async def capture_observations_dom():
    """使用 Playwright 读取 /observations 页面真实 DOM 文本"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("ERROR: Playwright not installed. Run: pip install playwright && playwright install chromium")
        return False
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # 访问页面
            print("访问 http://localhost:3010/observations")
            await page.goto("http://localhost:3010/observations", wait_until="networkidle", timeout=30000)
            
            # 等待页面加载
            await page.wait_for_timeout(2000)
            
            # 读取页面文本
            dom_output = []
            
            # 页面标题
            title = await page.locator("h1").first.text_content()
            dom_output.append(f"# 页面标题\n\n{title}\n")
            
            # 副标题
            subtitle = await page.locator("h1 + p").text_content()
            dom_output.append(f"# 副标题\n\n{subtitle}\n")
            
            # Filter tabs
            tabs = await page.locator("button").all()
            tab_texts = []
            for tab in tabs[:3]:  # 前3个是 filter tabs
                text = await tab.text_content()
                tab_texts.append(text.strip())
            dom_output.append(f"# Filter Tabs\n\n{' | '.join(tab_texts)}\n")
            
            # 检查是否有持仓卡片
            cards = await page.locator("div[style*='cursor: pointer']").all()
            
            if len(cards) == 0:
                # 空状态
                empty_title = await page.locator("p").filter(has_text="暂无").text_content()
                empty_text = await page.get_by_text("去 Workbench").text_content()
                dom_output.append(f"# 空状态\n\n{empty_title}\n\n{empty_text}\n")
            else:
                # 持仓卡片
                dom_output.append(f"# 持仓卡片 (共 {len(cards)} 个)\n\n")
                
                for i, card in enumerate(cards[:3], 1):  # 只读前3个
                    card_text = await card.text_content()
                    dom_output.append(f"## 卡片 {i}\n\n```\n{card_text.strip()}\n```\n\n")
                    
                    # 尝试提取关键信息
                    try:
                        # 股票名称和代码
                        h3 = await card.locator("h3").text_content()
                        dom_output.append(f"**股票:** {h3}\n\n")
                        
                        # Badge
                        badge = await card.locator("span").first.text_content()
                        dom_output.append(f"**信号 Badge:** {badge}\n\n")
                        
                        # 今日动作
                        action_label = await card.get_by_text("今日动作").text_content() if await card.get_by_text("今日动作").count() > 0 else None
                        if action_label:
                            action_section = await card.locator("div").filter(has_text="今日动作").text_content()
                            dom_output.append(f"**今日动作区域:** {action_section}\n\n")
                    except:
                        pass
            
            # 保存到文件
            output_text = "\n".join(dom_output)
            output_path = "docs/verification/p2-1a-observations-dom-output.md"
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("# P2-1A Observations 页面 - 真实 DOM 文本证据\n\n")
                f.write("**数据来源:** 真实浏览器 Playwright 读取\n\n")
                f.write("**URL:** http://localhost:3010/observations\n\n")
                f.write("---\n\n")
                f.write(output_text)
            
            print(f"[OK] Saved: {output_path}")
            
            # 截图保存
            await page.screenshot(path="docs/verification/p2-1a-observations-page.png")
            print("[OK] Saved screenshot: p2-1a-observations-page.png")
            
            await browser.close()
            return True
            
        except Exception as e:
            print(f"ERROR: {e}")
            await browser.close()
            return False


if __name__ == "__main__":
    print("=== P2-1A 真实浏览器 DOM 验证 ===\n")
    
    success = asyncio.run(capture_observations_dom())
    
    if success:
        print("\n[OK] DOM 验证完成")
        sys.exit(0)
    else:
        print("\n[BLOCKED] DOM 验证失败")
        sys.exit(1)
