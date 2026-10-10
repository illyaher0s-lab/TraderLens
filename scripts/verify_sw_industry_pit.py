"""SW Industry PIT Feasibility Verification - Read-only audit.

Verifies if Tushare SW industry membership can replace vendor industry field.
No modifications to code, templates, or qualification results.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env.local
env_file = Path(__file__).parent.parent / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = value

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient


def verify_sw_industry_pit():
    """Read-only verification of SW industry PIT availability."""
    config = TushareConfig.from_env()
    client = TushareClient(config)
    
    report = []
    request_count = 0
    
    # Check dates
    check_dates = ["20160104", "20200309", "20241017", "20260710"]
    
    report.append("# SW Industry PIT Feasibility Verification\n")
    report.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**Endpoint:** {config.api_url}\n")
    report.append(f"**Check dates:** {', '.join(check_dates)}\n\n")
    
    # 1. Get SW classifications
    report.append("## 1. SW Classifications\n\n")
    
    sw_versions = []
    for src in ["SW2014", "SW2021"]:
        try:
            df = client.pro.index_classify(level="L1", src=src)
            request_count += 1
            
            if df is None or df.empty:
                report.append(f"**{src}:** unavailable\n")
                continue
            
            l1_count = len(df)
            report.append(f"**{src}:** {l1_count} L1 industries\n")
            
            sw_versions.append({
                "src": src,
                "l1_codes": df["index_code"].tolist(),
                "l1_names": df["industry_name"].tolist()
            })
            
            # Sample
            report.append(f"- Sample: {df['index_code'].iloc[0]} {df['industry_name'].iloc[0]}\n")
            
        except Exception as e:
            report.append(f"**{src}:** error: {str(e)}\n")
    
    report.append(f"\n**Total requests:** {request_count}\n\n")
    
    if not sw_versions:
        report.append("## Conclusion\n\n**Status:** unavailable\n")
        report.append("**Reason:** No SW classifications available\n")
        return "\n".join(report), request_count
    
    # 2. Check member schema
    report.append("## 2. Member Schema\n\n")
    
    # Sample query to check schema
    sample_stock = "600000.SH"
    try:
        df_y = client.pro.index_member_all(ts_code=sample_stock, is_new="Y")
        request_count += 1
        
        if df_y is not None and not df_y.empty:
            fields = df_y.columns.tolist()
            report.append(f"**Fields:** {', '.join(fields)}\n")
            report.append(f"**Required fields present:** ")
            
            required = ["ts_code", "l1_code", "l1_name", "in_date", "out_date", "is_new"]
            missing = [f for f in required if f not in fields]
            
            if missing:
                report.append(f"❌ Missing: {', '.join(missing)}\n")
            else:
                report.append("✓\n")
        else:
            report.append("**Schema check:** failed (empty response)\n")
    except Exception as e:
        report.append(f"**Schema check:** error: {str(e)}\n")
    
    report.append(f"\n**Total requests:** {request_count}\n\n")
    
    # 3. Coverage check
    report.append("## 3. Coverage Check\n\n")
    
    # Sample 10 stocks
    sample_stocks = [
        "600000.SH",  # Main board
        "000001.SZ",  # Main board
        "300750.SZ",  # ChiNext
        "688001.SH",  # STAR
        "600519.SH",  # Maotai
    ]
    
    truncations = []
    coverage_gaps = []
    
    for stock in sample_stocks:
        report.append(f"### {stock}\n\n")
        
        # Query is_new Y and N
        try:
            df_y = client.pro.index_member_all(ts_code=stock, is_new="Y")
            request_count += 1
            
            df_n = client.pro.index_member_all(ts_code=stock, is_new="N")
            request_count += 1
            
            if request_count >= 78:
                report.append(f"\n**Request limit reached: {request_count}/80**\n")
                break
            
            y_count = 0 if df_y is None or df_y.empty else len(df_y)
            n_count = 0 if df_n is None or df_n.empty else len(df_n)
            
            report.append(f"- is_new=Y: {y_count} rows\n")
            report.append(f"- is_new=N: {n_count} rows\n")
            
            # Check for 5000 truncation
            if y_count == 5000:
                truncations.append(f"{stock} is_new=Y")
                report.append(f"- ⚠️ suspected_truncation (is_new=Y)\n")
            if n_count == 5000:
                truncations.append(f"{stock} is_new=N")
                report.append(f"- ⚠️ suspected_truncation (is_new=N)\n")
            
            # Check coverage for each date
            if y_count > 0 or n_count > 0:
                import pandas as pd
                all_records = []
                if y_count > 0:
                    all_records.append(df_y)
                if n_count > 0:
                    all_records.append(df_n)
                
                combined = pd.concat(all_records, ignore_index=True)
                
                for check_date in check_dates:
                    # Filter by in_date <= check_date AND (out_date IS NULL OR out_date >= check_date)
                    valid = combined[
                        (combined["in_date"].astype(str) <= check_date) &
                        ((combined["out_date"].isna()) | (combined["out_date"].astype(str) >= check_date))
                    ]
                    
                    if valid.empty:
                        report.append(f"- {check_date}: NO MEMBERSHIP\n")
                    else:
                        l1_codes = valid["l1_code"].unique()
                        if len(l1_codes) > 1:
                            report.append(f"- {check_date}: ❌ CONFLICT ({len(l1_codes)} industries)\n")
                            coverage_gaps.append(f"{stock} on {check_date}: multiple industries")
                        else:
                            l1_name = valid["l1_name"].iloc[0]
                            report.append(f"- {check_date}: {l1_codes[0]} {l1_name}\n")
            else:
                report.append(f"- No membership records\n")
                coverage_gaps.append(f"{stock}: no records")
            
            report.append("\n")
            
        except Exception as e:
            report.append(f"- Error: {str(e)}\n\n")
            coverage_gaps.append(f"{stock}: query error")
        
        if request_count >= 78:
            break
    
    report.append(f"**Total requests:** {request_count}\n\n")
    
    # 4. Conclusion
    report.append("## 4. Conclusion\n\n")
    report.append(f"**Total requests:** {request_count}/80\n")
    report.append(f"**SW versions found:** {len(sw_versions)}\n")
    
    if truncations:
        report.append(f"**Status:** suspected_truncation\n")
        report.append(f"**Truncations:** {len(truncations)}\n")
        for t in truncations:
            report.append(f"- {t}\n")
    elif coverage_gaps:
        report.append(f"**Status:** unavailable\n")
        report.append(f"**Gaps:** {len(coverage_gaps)}\n")
        for g in coverage_gaps:
            report.append(f"- {g}\n")
    else:
        report.append(f"**Status:** feasible_for_full_collection\n")
        report.append(f"**Coverage:** Complete for sampled stocks and dates\n")
    
    report.append("\n**Note:** This is a read-only feasibility check. Full collection and formal qualification required before use.\n")
    
    return "\n".join(report), request_count


if __name__ == "__main__":
    report_content, req_count = verify_sw_industry_pit()
    
    output_path = Path(__file__).parent.parent / "docs/verification/SW_INDUSTRY_PIT_FEASIBILITY.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_content, encoding="utf-8")
    
    print(f"Report written to: {output_path}")
    print(f"Total requests: {req_count}")
    
    # Exit code based on conclusion
    if "unavailable" in report_content or "suspected_truncation" in report_content:
        sys.exit(1)
    else:
        sys.exit(0)
