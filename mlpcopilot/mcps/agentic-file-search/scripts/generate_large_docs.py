#!/usr/bin/env python3
"""
Generate a large set of interconnected legal documents for testing.
Creates 25 documents, each 3-5 pages, with extensive cross-references.
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

OUTPUT_DIR = "data/large_acquisition"

# Document metadata with cross-references
DOCUMENTS = {
    "01_master_agreement": {
        "title": "MASTER ACQUISITION AGREEMENT",
        "refs": ["02_schedules", "03_exhibits", "04_disclosure_schedules", "05_ancillary_agreements"],
        "pages": 5
    },
    "02_schedules": {
        "title": "SCHEDULES TO ACQUISITION AGREEMENT", 
        "refs": ["01_master_agreement", "06_ip_schedule", "07_employee_schedule", "08_contract_schedule"],
        "pages": 4
    },
    "03_exhibits": {
        "title": "EXHIBITS TO ACQUISITION AGREEMENT",
        "refs": ["01_master_agreement", "09_escrow_agreement", "10_stock_purchase"],
        "pages": 3
    },
    "04_disclosure_schedules": {
        "title": "SELLER DISCLOSURE SCHEDULES",
        "refs": ["01_master_agreement", "11_financial_statements", "12_litigation_schedule"],
        "pages": 5
    },
    "05_ancillary_agreements": {
        "title": "ANCILLARY AGREEMENTS INDEX",
        "refs": ["13_nda", "14_non_compete", "15_consulting_agreement", "16_transition_services"],
        "pages": 2
    },
    "06_ip_schedule": {
        "title": "SCHEDULE 3.12 - INTELLECTUAL PROPERTY",
        "refs": ["01_master_agreement", "17_patent_assignments", "18_trademark_registrations"],
        "pages": 4
    },
    "07_employee_schedule": {
        "title": "SCHEDULE 3.15 - EMPLOYEE MATTERS",
        "refs": ["01_master_agreement", "19_retention_agreements", "20_benefit_plans"],
        "pages": 4
    },
    "08_contract_schedule": {
        "title": "SCHEDULE 3.13 - MATERIAL CONTRACTS",
        "refs": ["01_master_agreement", "21_customer_contracts", "22_vendor_contracts"],
        "pages": 5
    },
    "09_escrow_agreement": {
        "title": "ESCROW AGREEMENT",
        "refs": ["01_master_agreement", "03_exhibits", "11_financial_statements"],
        "pages": 4
    },
    "10_stock_purchase": {
        "title": "STOCK PURCHASE DETAILS - EXHIBIT B",
        "refs": ["01_master_agreement", "11_financial_statements"],
        "pages": 3
    },
    "11_financial_statements": {
        "title": "AUDITED FINANCIAL STATEMENTS",
        "refs": ["04_disclosure_schedules", "23_audit_report"],
        "pages": 6
    },
    "12_litigation_schedule": {
        "title": "SCHEDULE 3.9 - LITIGATION AND CLAIMS",
        "refs": ["04_disclosure_schedules", "24_legal_opinion"],
        "pages": 3
    },
    "13_nda": {
        "title": "NON-DISCLOSURE AGREEMENT",
        "refs": ["01_master_agreement"],
        "pages": 3
    },
    "14_non_compete": {
        "title": "NON-COMPETITION AGREEMENT",
        "refs": ["01_master_agreement", "07_employee_schedule"],
        "pages": 3
    },
    "15_consulting_agreement": {
        "title": "CONSULTING AGREEMENT - FOUNDER",
        "refs": ["01_master_agreement", "07_employee_schedule", "19_retention_agreements"],
        "pages": 4
    },
    "16_transition_services": {
        "title": "TRANSITION SERVICES AGREEMENT",
        "refs": ["01_master_agreement", "25_closing_checklist"],
        "pages": 4
    },
    "17_patent_assignments": {
        "title": "PATENT ASSIGNMENT AGREEMENTS",
        "refs": ["06_ip_schedule", "01_master_agreement"],
        "pages": 3
    },
    "18_trademark_registrations": {
        "title": "TRADEMARK REGISTRATION SCHEDULE",
        "refs": ["06_ip_schedule"],
        "pages": 2
    },
    "19_retention_agreements": {
        "title": "KEY EMPLOYEE RETENTION AGREEMENTS",
        "refs": ["07_employee_schedule", "15_consulting_agreement"],
        "pages": 4
    },
    "20_benefit_plans": {
        "title": "EMPLOYEE BENEFIT PLAN SCHEDULE",
        "refs": ["07_employee_schedule"],
        "pages": 3
    },
    "21_customer_contracts": {
        "title": "MAJOR CUSTOMER CONTRACT SUMMARIES",
        "refs": ["08_contract_schedule", "01_master_agreement"],
        "pages": 5
    },
    "22_vendor_contracts": {
        "title": "MAJOR VENDOR CONTRACT SUMMARIES",
        "refs": ["08_contract_schedule"],
        "pages": 3
    },
    "23_audit_report": {
        "title": "INDEPENDENT AUDITOR'S REPORT",
        "refs": ["11_financial_statements", "04_disclosure_schedules"],
        "pages": 4
    },
    "24_legal_opinion": {
        "title": "LEGAL OPINION LETTER",
        "refs": ["01_master_agreement", "12_litigation_schedule", "06_ip_schedule"],
        "pages": 3
    },
    "25_closing_checklist": {
        "title": "CLOSING CHECKLIST AND CONDITIONS",
        "refs": ["01_master_agreement", "09_escrow_agreement", "16_transition_services", 
                 "17_patent_assignments", "21_customer_contracts"],
        "pages": 4
    }
}

def generate_content(doc_id: str, meta: dict) -> list:
    """Generate realistic legal document content."""
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, spaceAfter=20)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=12, spaceAfter=10)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, spaceAfter=8, leading=14)
    
    content = []
    
    # Title
    content.append(Paragraph(meta["title"], title_style))
    content.append(Spacer(1, 0.3*inch))
    
    # Document intro with cross-references
    refs_text = ", ".join([f"Document: {DOCUMENTS[r]['title']}" for r in meta["refs"][:3]])
    intro = f"""
    This document is part of the acquisition transaction between GlobalTech Corporation ("Buyer") 
    and InnovateTech Solutions, Inc. ("Seller") dated as of February 15, 2025. This document should 
    be read in conjunction with {refs_text}, and all other transaction documents.
    """
    content.append(Paragraph(intro.strip(), body_style))
    content.append(Spacer(1, 0.2*inch))
    
    # Generate sections based on document type
    sections = generate_sections(doc_id, meta)
    for section_title, section_content in sections:
        content.append(Paragraph(section_title, heading_style))
        for para in section_content:
            content.append(Paragraph(para, body_style))
        content.append(Spacer(1, 0.15*inch))
    
    return content

def generate_sections(doc_id: str, meta: dict) -> list:
    """Generate document-specific sections with legal content."""
    sections = []
    
    # Add document-specific content
    if "master_agreement" in doc_id:
        sections = [
            ("ARTICLE I - DEFINITIONS", [
                "1.1 'Acquisition' means the purchase by Buyer of all outstanding capital stock of Seller.",
                "1.2 'Purchase Price' means One Hundred Twenty-Five Million Dollars ($125,000,000), subject to adjustments.",
                "1.3 'Closing Date' means April 1, 2025, or such other date as mutually agreed.",
                "1.4 'Material Adverse Effect' means any change that is materially adverse to the business of Seller.",
                "1.5 'Knowledge of Seller' means the actual knowledge of the officers listed in Schedule 1.5.",
            ]),
            ("ARTICLE II - PURCHASE AND SALE", [
                "2.1 Subject to the terms hereof, Seller agrees to sell and Buyer agrees to purchase all Shares.",
                "2.2 The Purchase Price shall be paid as follows: (a) $80,000,000 in cash at Closing; "
                "(b) $30,000,000 in Buyer common stock per Document: Stock Purchase Details - Exhibit B; "
                "(c) $15,000,000 in escrow per Document: Escrow Agreement.",
                "2.3 Purchase Price adjustments are detailed in Document: Audited Financial Statements.",
                "2.4 Working capital target is $8,500,000 as calculated per Schedule 2.4.",
            ]),
            ("ARTICLE III - REPRESENTATIONS AND WARRANTIES", [
                "3.1 Organization. Seller is duly organized under Delaware law.",
                "3.9 Litigation. Except as set forth in Document: Schedule 3.9 - Litigation and Claims, "
                "there are no pending legal proceedings against Seller.",
                "3.12 Intellectual Property. All IP is listed in Document: Schedule 3.12 - Intellectual Property. "
                "Patent assignments are documented in Document: Patent Assignment Agreements.",
                "3.13 Material Contracts. All contracts exceeding $100,000 annually are in Document: Schedule 3.13 - Material Contracts.",
                "3.15 Employees. Employee matters are disclosed in Document: Schedule 3.15 - Employee Matters.",
            ]),
            ("ARTICLE IV - COVENANTS", [
                "4.1 Conduct of Business. Prior to Closing, Seller shall operate in ordinary course.",
                "4.2 Access. Seller shall provide Buyer access to facilities, books, and records.",
                "4.3 Confidentiality. Parties shall comply with Document: Non-Disclosure Agreement.",
                "4.4 Non-Competition. Key employees shall execute Document: Non-Competition Agreement.",
            ]),
            ("ARTICLE V - CONDITIONS TO CLOSING", [
                "5.1 Buyer's conditions: (a) accuracy of representations; (b) material consents obtained; "
                "(c) no Material Adverse Effect; (d) receipt of Document: Legal Opinion Letter.",
                "5.2 Regulatory approvals as specified in Document: Closing Checklist and Conditions.",
                "5.3 Third-party consents from customers in Document: Major Customer Contract Summaries.",
            ]),
        ]
    elif "financial" in doc_id:
        sections = [
            ("BALANCE SHEET", [
                "As of December 31, 2024:",
                "Total Assets: $47,250,000 (Current: $18,500,000; Non-current: $28,750,000)",
                "Total Liabilities: $12,300,000 (Current: $8,200,000; Long-term: $4,100,000)",
                "Stockholders' Equity: $34,950,000",
                "Working Capital: $10,300,000 (above target of $8,500,000 per Document: Master Acquisition Agreement)",
            ]),
            ("INCOME STATEMENT", [
                "For fiscal year ended December 31, 2024:",
                "Total Revenue: $52,400,000 (SaaS: $41,920,000; Professional Services: $10,480,000)",
                "Cost of Revenue: $15,720,000 (Gross Margin: 70%)",
                "Operating Expenses: $28,600,000 (R&D: $12,100,000; S&M: $11,500,000; G&A: $5,000,000)",
                "Operating Income: $8,080,000 (EBITDA: $11,200,000)",
                "Net Income: $6,464,000",
            ]),
            ("REVENUE BREAKDOWN BY CUSTOMER", [
                "Top 5 customers represent 62% of revenue (see Document: Major Customer Contract Summaries):",
                "1. MegaCorp Industries: $12,576,000 (24%) - Contract through 2027",
                "2. GlobalBank Holdings: $8,384,000 (16%) - Renewal pending",
                "3. HealthFirst Systems: $5,240,000 (10%) - Multi-year agreement",
                "4. RetailMax Inc.: $3,668,000 (7%) - Expansion discussion ongoing",
                "5. TechPrime Solutions: $2,620,000 (5%) - New customer 2024",
            ]),
            ("NOTES TO FINANCIAL STATEMENTS", [
                "Note 1: Significant Accounting Policies - Revenue recognized per ASC 606.",
                "Note 2: Deferred Revenue of $4,200,000 represents prepaid annual subscriptions.",
                "Note 3: Contingent liabilities detailed in Document: Schedule 3.9 - Litigation and Claims.",
                "Note 4: Related party transactions with founder disclosed in Document: Consulting Agreement - Founder.",
            ]),
        ]
    elif "ip_schedule" in doc_id or "patent" in doc_id:
        sections = [
            ("PATENTS", [
                "Seller owns or has rights to the following patents:",
                "US Patent 10,123,456 - 'Machine Learning System for Predictive Analytics' - Issued 2021",
                "US Patent 10,234,567 - 'Distributed Data Processing Architecture' - Issued 2022",
                "US Patent 10,345,678 - 'Real-time Anomaly Detection Method' - Issued 2023",
                "Pending: US Application 17/456,789 - 'Automated Workflow Optimization' - Filed 2024",
                "Assignment agreements in Document: Patent Assignment Agreements.",
            ]),
            ("TRADEMARKS", [
                "Registered trademarks (see Document: Trademark Registration Schedule):",
                "INNOVATETECH (word mark) - Reg. No. 5,123,456 - Software services",
                "INNOVATETECH (logo) - Reg. No. 5,234,567 - Software services",
                "DATAFLOW PRO - Reg. No. 5,345,678 - Data analytics software",
            ]),
            ("TRADE SECRETS AND KNOW-HOW", [
                "Seller maintains trade secrets including proprietary algorithms and processes.",
                "All employees have executed invention assignment agreements per Document: Schedule 3.15 - Employee Matters.",
                "Key technical personnel retention addressed in Document: Key Employee Retention Agreements.",
            ]),
        ]
    elif "employee" in doc_id or "retention" in doc_id:
        sections = [
            ("EMPLOYEE CENSUS", [
                "Total Employees: 127 (Full-time: 120; Part-time: 7)",
                "Engineering: 68 employees (Senior: 24; Mid-level: 32; Junior: 12)",
                "Sales & Marketing: 28 employees",
                "Customer Success: 18 employees",
                "G&A: 13 employees",
            ]),
            ("KEY EMPLOYEES", [
                "The following are Key Employees subject to Document: Key Employee Retention Agreements:",
                "1. Dr. Sarah Chen - CTO - 15 years experience - Retention bonus: $1,200,000",
                "2. Michael Rodriguez - VP Engineering - Leads 45-person team - Retention: $800,000",
                "3. Jennifer Walsh - VP Sales - $18M quota achievement - Retention: $600,000",
                "4. David Kim - Principal Architect - Core platform expertise - Retention: $500,000",
                "5. Amanda Foster - VP Customer Success - 95% retention rate - Retention: $400,000",
                "Founder consulting terms in Document: Consulting Agreement - Founder.",
            ]),
            ("BENEFIT PLANS", [
                "Active benefit plans (details in Document: Employee Benefit Plan Schedule):",
                "401(k) Plan - Company match 4% - $2.1M annual cost",
                "Health Insurance - PPO and HMO options - $1.8M annual cost",
                "Stock Option Plan - 2,500,000 shares reserved - 1,800,000 granted",
                "Treatment of equity awards addressed in Document: Master Acquisition Agreement Section 2.6.",
            ]),
        ]
    elif "customer" in doc_id or "contract_schedule" in doc_id:
        sections = [
            ("MATERIAL CUSTOMER CONTRACTS", [
                "Contracts with annual value exceeding $500,000:",
                "",
                "1. MEGACORP INDUSTRIES - Master Services Agreement",
                "   Annual Value: $12,576,000 | Term: Through December 2027",
                "   Change of Control: Consent required (OBTAINED February 8, 2025)",
                "   Renewal Terms: Auto-renew with 90-day notice",
                "",
                "2. GLOBALBANK HOLDINGS - Enterprise License Agreement",
                "   Annual Value: $8,384,000 | Term: Through June 2025",
                "   Change of Control: 60-day notice required (PROVIDED January 15, 2025)",
                "   Renewal: Currently in negotiation for 3-year extension",
                "",
                "3. HEALTHFIRST SYSTEMS - SaaS Subscription Agreement",
                "   Annual Value: $5,240,000 | Term: Through December 2026",
                "   Change of Control: No restrictions",
                "",
                "See Document: Closing Checklist and Conditions for consent status.",
            ]),
            ("CONSENT REQUIREMENTS", [
                "Customer consents required for acquisition (per Document: Master Acquisition Agreement):",
                "- MegaCorp Industries: OBTAINED (see Exhibit A hereto)",
                "- GlobalBank Holdings: NOTICE PROVIDED (awaiting acknowledgment)",
                "- Other customers: No consent required",
                "Risk assessment in Document: Legal Opinion Letter.",
            ]),
        ]
    elif "litigation" in doc_id:
        sections = [
            ("PENDING LITIGATION", [
                "1. Smith v. InnovateTech Solutions, Inc.",
                "   Court: California Superior Court, Santa Clara County",
                "   Claims: Wrongful termination, discrimination",
                "   Status: Discovery phase; trial set for September 2025",
                "   Exposure: $150,000 - $350,000 (covered by insurance)",
                "   Opinion: See Document: Legal Opinion Letter",
                "",
                "2. DataTech LLC v. InnovateTech Solutions, Inc.",
                "   Court: US District Court, Northern District of California",
                "   Claims: Patent infringement (US Patent 9,876,543)",
                "   Status: Motion to dismiss pending; hearing March 2025",
                "   Exposure: Preliminary assessment $500,000 - $2,000,000",
                "   IP validity analysis in Document: Schedule 3.12 - Intellectual Property",
            ]),
            ("THREATENED CLAIMS", [
                "Demand letter received from former contractor re: unpaid invoices ($45,000).",
                "Resolution expected prior to Closing per Document: Closing Checklist and Conditions.",
            ]),
            ("INSURANCE COVERAGE", [
                "D&O Insurance: $5,000,000 limit | Deductible: $50,000",
                "E&O Insurance: $3,000,000 limit | Deductible: $25,000",
                "General Liability: $2,000,000 limit",
            ]),
        ]
    elif "closing" in doc_id:
        sections = [
            ("PRE-CLOSING CONDITIONS", [
                "The following conditions must be satisfied prior to Closing:",
                "",
                "1. REGULATORY APPROVALS",
                "   [X] HSR Filing - Early termination granted February 1, 2025",
                "   [X] State filings - Completed in all required jurisdictions",
                "",
                "2. THIRD-PARTY CONSENTS",
                "   [X] MegaCorp Industries - Obtained February 8, 2025",
                "   [ ] GlobalBank Holdings - Pending (expected by March 15)",
                "   Per Document: Major Customer Contract Summaries",
                "",
                "3. EMPLOYEE MATTERS",
                "   [X] Key employee retention agreements executed",
                "   [X] Founder consulting agreement finalized",
                "   Per Document: Key Employee Retention Agreements",
                "",
                "4. LEGAL DELIVERABLES",
                "   [X] Legal opinion - See Document: Legal Opinion Letter",
                "   [ ] Good standing certificates - Ordered",
            ]),
            ("CLOSING DELIVERABLES", [
                "SELLER DELIVERABLES:",
                "- Stock certificates endorsed in blank",
                "- Officer's certificate re: representations",
                "- Secretary's certificate with resolutions",
                "- IP assignments per Document: Patent Assignment Agreements",
                "- Third-party consents per above",
                "",
                "BUYER DELIVERABLES:",
                "- Cash payment: $80,000,000 by wire transfer",
                "- Stock consideration: 1,500,000 shares per Document: Stock Purchase Details - Exhibit B",
                "- Escrow deposit: $15,000,000 per Document: Escrow Agreement",
            ]),
            ("POST-CLOSING OBLIGATIONS", [
                "1. Transition services per Document: Transition Services Agreement (6 months)",
                "2. Earnout payments per Exhibit C to Document: Master Acquisition Agreement",
                "3. Escrow release schedule per Document: Escrow Agreement",
                "4. Employee benefit plan merger per Document: Employee Benefit Plan Schedule",
            ]),
        ]
    elif "escrow" in doc_id:
        sections = [
            ("ESCROW TERMS", [
                "Escrow Amount: $15,000,000 (12% of Purchase Price)",
                "Escrow Agent: First National Trust Company",
                "Term: 18 months from Closing Date",
                "",
                "Release Schedule:",
                "- 6 months: $5,000,000 released (absent claims)",
                "- 12 months: $5,000,000 released (absent claims)",
                "- 18 months: Remaining balance released",
                "",
                "Claims may be made for breaches of representations in Document: Master Acquisition Agreement.",
            ]),
            ("INDEMNIFICATION", [
                "Indemnification provisions per Article VII of Document: Master Acquisition Agreement:",
                "- Basket: $500,000 (1% of escrow)",
                "- Cap: $15,000,000 (escrow amount) for general reps",
                "- Fundamental reps: Full Purchase Price cap",
                "",
                "Specific indemnities for matters in Document: Schedule 3.9 - Litigation and Claims.",
            ]),
        ]
    elif "legal_opinion" in doc_id:
        sections = [
            ("OPINIONS RENDERED", [
                "Wilson & Associates LLP, counsel to Seller, renders the following opinions:",
                "",
                "1. Seller is a corporation duly organized under Delaware law.",
                "2. Seller has corporate power to execute Document: Master Acquisition Agreement.",
                "3. Transaction documents are valid and enforceable obligations.",
                "4. No conflicts with charter documents or material agreements.",
                "5. Based on review of Document: Schedule 3.9 - Litigation and Claims, pending "
                "litigation does not pose material risk to transaction.",
                "6. IP matters reviewed per Document: Schedule 3.12 - Intellectual Property; "
                "no infringement claims other than disclosed.",
            ]),
            ("QUALIFICATIONS AND ASSUMPTIONS", [
                "This opinion is subject to standard qualifications regarding:",
                "- Bankruptcy and insolvency laws",
                "- Equitable principles",
                "- Public policy considerations",
                "",
                "We have relied upon certificates from officers of Seller and representations "
                "in Document: Seller Disclosure Schedules.",
            ]),
        ]
    elif "audit" in doc_id:
        sections = [
            ("INDEPENDENT AUDITOR'S REPORT", [
                "To the Board of Directors of InnovateTech Solutions, Inc.:",
                "",
                "We have audited the accompanying financial statements, which comprise the "
                "balance sheet as of December 31, 2024, and the related statements of income, "
                "comprehensive income, stockholders' equity, and cash flows for the year then ended.",
                "",
                "OPINION",
                "In our opinion, the financial statements present fairly, in all material respects, "
                "the financial position of InnovateTech Solutions, Inc. as of December 31, 2024, "
                "in accordance with accounting principles generally accepted in the United States.",
            ]),
            ("KEY AUDIT MATTERS", [
                "1. REVENUE RECOGNITION",
                "   SaaS revenue recognized ratably over subscription period per ASC 606.",
                "   Deferred revenue of $4,200,000 verified to customer contracts.",
                "",
                "2. STOCK-BASED COMPENSATION",
                "   Options valued using Black-Scholes model.",
                "   Expense of $2,100,000 recorded in accordance with ASC 718.",
                "",
                "3. CONTINGENCIES",
                "   Litigation matters reviewed with counsel (see Document: Schedule 3.9 - Litigation and Claims).",
                "   Accruals of $350,000 determined to be appropriate.",
            ]),
        ]
    else:
        # Generic sections for other documents
        sections = [
            ("OVERVIEW", [
                f"This {meta['title']} is executed in connection with the acquisition transaction.",
                f"Reference documents: {', '.join([DOCUMENTS[r]['title'] for r in meta['refs'][:2]])}.",
            ]),
            ("TERMS AND CONDITIONS", [
                "Standard terms apply as set forth in the Master Acquisition Agreement.",
                "Amendments require written consent of all parties.",
            ]),
            ("MISCELLANEOUS", [
                "Governing Law: State of Delaware",
                "Dispute Resolution: Arbitration in San Francisco, California",
                "Notices: As specified in Master Acquisition Agreement",
            ]),
        ]
    
    # Add boilerplate to reach target page count
    for i in range(meta["pages"] - 2):
        sections.append((f"SECTION {len(sections) + 1}", [
            f"Additional provisions related to {meta['title']}.",
            "All terms defined in Document: Master Acquisition Agreement apply herein.",
            f"Cross-reference: See {DOCUMENTS[meta['refs'][i % len(meta['refs'])]]['title']} for related provisions.",
            "The parties acknowledge receipt of all schedules and exhibits referenced herein.",
            "This section shall survive the Closing Date as specified in Article VIII of the Master Agreement.",
        ]))
    
    return sections


def create_pdf(doc_id: str, meta: dict, output_dir: str):
    """Create a PDF document."""
    filepath = os.path.join(output_dir, f"{doc_id}.pdf")
    doc = SimpleDocTemplate(filepath, pagesize=letter,
                           topMargin=0.75*inch, bottomMargin=0.75*inch,
                           leftMargin=1*inch, rightMargin=1*inch)
    content = generate_content(doc_id, meta)
    doc.build(content)
    print(f"  Created: {filepath}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print(f"\nGenerating {len(DOCUMENTS)} large documents in {OUTPUT_DIR}/\n")
    
    for doc_id, meta in DOCUMENTS.items():
        create_pdf(doc_id, meta, OUTPUT_DIR)
    
    # Create test questions
    questions_path = os.path.join(OUTPUT_DIR, "TEST_QUESTIONS.md")
    with open(questions_path, "w") as f:
        f.write("""# Test Questions for Large Document Set

## Document Overview
- 25 interconnected documents
- Each document 3-6 pages
- Extensive cross-references between documents
- Total content: ~100+ pages

## Test Questions

### Level 1: Single Document (Easy)
```bash
uv run explore --task "Look in data/large_acquisition/. What is the total purchase price?"
uv run explore --task "Look in data/large_acquisition/. Who is the CTO and what is their retention bonus?"
uv run explore --task "Look in data/large_acquisition/. What patents does the company own?"
```

### Level 2: Cross-Reference Required (Medium)
```bash
uv run explore --task "Look in data/large_acquisition/. What customer consents are required and what is their status?"
uv run explore --task "Look in data/large_acquisition/. What is the total litigation exposure and is it covered by insurance?"
uv run explore --task "Look in data/large_acquisition/. How is the purchase price being paid and what are the escrow terms?"
```

### Level 3: Multi-Document Synthesis (Hard)
```bash
uv run explore --task "Look in data/large_acquisition/. What are all the conditions that must be satisfied before closing and what is the status of each?"
uv run explore --task "Look in data/large_acquisition/. Provide a complete picture of MegaCorp's relationship with the company - revenue, contract terms, consent status, and any risks."
uv run explore --task "Look in data/large_acquisition/. What are all the financial terms of this deal including adjustments, escrow, earnouts, and stock?"
```

### Level 4: Deep Cross-Reference (Expert)
```bash
uv run explore --task "Look in data/large_acquisition/. Trace all references to the Legal Opinion Letter - what documents cite it and what opinions does it provide?"
uv run explore --task "Look in data/large_acquisition/. Create a complete picture of IP assets - patents, trademarks, assignments, and any related risks or litigation."
uv run explore --task "Look in data/large_acquisition/. What happens after closing? List all post-closing obligations, their timelines, and related documents."
```
""")
    print(f"  Created: {questions_path}")
    
    # Summary
    total_pages = sum(m["pages"] for m in DOCUMENTS.values())
    total_refs = sum(len(m["refs"]) for m in DOCUMENTS.values())
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Documents created: {len(DOCUMENTS)}")
    print(f"  Total pages: ~{total_pages}")
    print(f"  Cross-references: {total_refs}")
    print(f"  Output directory: {OUTPUT_DIR}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

