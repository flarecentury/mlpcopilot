#!/usr/bin/env python3
"""
Generate test PDF documents for testing the two-stage document exploration approach.

Scenario: TechCorp's acquisition of StartupXYZ
Documents have cross-references to test the agent's ability to follow document relationships.
"""

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import os

OUTPUT_DIR = "data/test_acquisition"

DOCUMENTS = {
    "01_acquisition_agreement.pdf": {
        "title": "ACQUISITION AGREEMENT",
        "content": """
        <b>ACQUISITION AGREEMENT</b><br/><br/>
        
        This Acquisition Agreement ("Agreement") is entered into as of January 15, 2025, 
        by and between TechCorp Industries, Inc. ("Buyer") and StartupXYZ LLC ("Seller").<br/><br/>
        
        <b>ARTICLE I - DEFINITIONS</b><br/><br/>
        
        1.1 "Acquisition" means the purchase of all outstanding shares of Seller by Buyer.<br/>
        1.2 "Purchase Price" means $45,000,000 USD as detailed in <b>Exhibit A - Financial Terms</b>.<br/>
        1.3 "Closing Date" means March 1, 2025, subject to conditions in Article IV.<br/>
        1.4 "Employee Matters" shall be governed by <b>Schedule 3 - Employee Transition Plan</b>.<br/><br/>
        
        <b>ARTICLE II - PURCHASE AND SALE</b><br/><br/>
        
        2.1 Subject to the terms and conditions of this Agreement, Seller agrees to sell, 
        and Buyer agrees to purchase, all of the issued and outstanding shares of Seller.<br/><br/>
        
        2.2 The Purchase Price shall be paid as follows:<br/>
        (a) $30,000,000 in cash at Closing<br/>
        (b) $10,000,000 in Buyer's common stock (see <b>Exhibit B - Stock Valuation</b>)<br/>
        (c) $5,000,000 in earnout payments (see <b>Exhibit C - Earnout Terms</b>)<br/><br/>
        
        <b>ARTICLE III - REPRESENTATIONS AND WARRANTIES</b><br/><br/>
        
        3.1 Seller represents and warrants that the financial statements provided in 
        <b>Document: Due Diligence Report</b> are accurate and complete.<br/><br/>
        
        3.2 Seller represents that all intellectual property is properly documented in 
        <b>Schedule 1 - IP Assets</b> and is free of encumbrances as certified in 
        <b>Document: IP Certification Letter</b>.<br/><br/>
        
        3.3 All material contracts are listed in <b>Schedule 2 - Material Contracts</b>.<br/><br/>
        
        <b>ARTICLE IV - CONDITIONS TO CLOSING</b><br/><br/>
        
        4.1 Buyer's obligation to close is subject to:<br/>
        (a) Receipt of regulatory approval as documented in <b>Document: Regulatory Approval Letter</b><br/>
        (b) Completion of due diligence per <b>Document: Due Diligence Report</b><br/>
        (c) No material adverse change as defined in Section 1.5<br/><br/>
        
        4.2 Both parties acknowledge the risks identified in <b>Document: Risk Assessment Memo</b>.<br/><br/>
        
        <b>ARTICLE V - CONFIDENTIALITY</b><br/><br/>
        
        5.1 This Agreement is subject to the terms of the <b>Document: Non-Disclosure Agreement</b> 
        executed between the parties on October 1, 2024.<br/><br/>
        
        IN WITNESS WHEREOF, the parties have executed this Agreement as of the date first above written.<br/><br/>
        
        _________________________<br/>
        TechCorp Industries, Inc.<br/>
        By: James Mitchell, CEO<br/><br/>
        
        _________________________<br/>
        StartupXYZ LLC<br/>
        By: Sarah Chen, Founder & CEO
        """
    },
    
    "02_due_diligence_report.pdf": {
        "title": "DUE DILIGENCE REPORT",
        "content": """
        <b>CONFIDENTIAL DUE DILIGENCE REPORT</b><br/><br/>
        
        <b>Prepared for:</b> TechCorp Industries, Inc.<br/>
        <b>Subject:</b> StartupXYZ LLC<br/>
        <b>Date:</b> December 20, 2024<br/>
        <b>Prepared by:</b> Morrison & Associates, LLP<br/><br/>
        
        <b>EXECUTIVE SUMMARY</b><br/><br/>
        
        This report summarizes our findings from the due diligence investigation of StartupXYZ LLC 
        in connection with the proposed acquisition described in the <b>Document: Acquisition Agreement</b>.<br/><br/>
        
        <b>1. FINANCIAL REVIEW</b><br/><br/>
        
        1.1 Revenue for FY2024: $12.3 million (growth of 45% YoY)<br/>
        1.2 EBITDA: $2.1 million (17% margin)<br/>
        1.3 Cash position: $3.2 million as of November 30, 2024<br/>
        1.4 Outstanding debt: $1.5 million (detailed in <b>Exhibit A - Financial Terms</b> of the Acquisition Agreement)<br/><br/>
        
        <b>KEY FINDING:</b> Financial statements are materially accurate. Minor adjustments 
        recommended as noted in <b>Document: Financial Adjustments Memo</b>.<br/><br/>
        
        <b>2. INTELLECTUAL PROPERTY</b><br/><br/>
        
        2.1 StartupXYZ holds 12 patents related to AI/ML technology<br/>
        2.2 All patents verified as valid per <b>Document: IP Certification Letter</b><br/>
        2.3 No pending litigation affecting IP (confirmed in <b>Document: Legal Opinion Letter</b>)<br/>
        2.4 Full IP inventory in <b>Schedule 1 - IP Assets</b> of the Acquisition Agreement<br/><br/>
        
        <b>3. EMPLOYEE MATTERS</b><br/><br/>
        
        3.1 Total employees: 47 (32 engineering, 8 sales, 7 operations)<br/>
        3.2 Key employee retention risk: HIGH for 5 senior engineers<br/>
        3.3 Retention bonuses recommended per <b>Schedule 3 - Employee Transition Plan</b><br/>
        3.4 No pending employment disputes<br/><br/>
        
        <b>4. MATERIAL CONTRACTS</b><br/><br/>
        
        4.1 23 active customer contracts reviewed (see <b>Schedule 2 - Material Contracts</b>)<br/>
        4.2 3 contracts contain change-of-control provisions requiring consent<br/>
        4.3 Largest customer (MegaCorp) accounts for 28% of revenue - concentration risk noted in 
        <b>Document: Risk Assessment Memo</b><br/><br/>
        
        <b>5. REGULATORY COMPLIANCE</b><br/><br/>
        
        5.1 Company is compliant with all applicable regulations<br/>
        5.2 HSR filing required - timeline in <b>Document: Regulatory Approval Letter</b><br/><br/>
        
        <b>6. RECOMMENDATIONS</b><br/><br/>
        
        Based on our findings, we recommend proceeding with the acquisition subject to:<br/>
        (a) Obtaining customer consents for change-of-control contracts<br/>
        (b) Implementing retention packages for key employees<br/>
        (c) Addressing items in <b>Document: Financial Adjustments Memo</b><br/><br/>
        
        Respectfully submitted,<br/>
        Morrison & Associates, LLP
        """
    },
    
    "03_ip_certification.pdf": {
        "title": "IP CERTIFICATION LETTER",
        "content": """
        <b>INTELLECTUAL PROPERTY CERTIFICATION LETTER</b><br/><br/>
        
        <b>Date:</b> December 15, 2024<br/>
        <b>To:</b> TechCorp Industries, Inc.<br/>
        <b>From:</b> PatentWatch Legal Services<br/>
        <b>Re:</b> IP Certification for StartupXYZ LLC Acquisition<br/><br/>
        
        Dear Mr. Mitchell,<br/><br/>
        
        In connection with the proposed acquisition of StartupXYZ LLC as described in the 
        <b>Document: Acquisition Agreement</b>, we have conducted a comprehensive review of 
        StartupXYZ's intellectual property portfolio.<br/><br/>
        
        <b>CERTIFICATION</b><br/><br/>
        
        We hereby certify the following:<br/><br/>
        
        <b>1. PATENTS</b><br/><br/>
        
        StartupXYZ owns 12 U.S. patents as listed in <b>Schedule 1 - IP Assets</b>:<br/>
        - US Patent 10,123,456: "Neural Network Optimization Method"<br/>
        - US Patent 10,234,567: "Distributed AI Training System"<br/>
        - US Patent 10,345,678: "Real-time Data Processing Pipeline"<br/>
        - [9 additional patents listed in Schedule 1]<br/><br/>
        
        All patents are valid, enforceable, and free of liens or encumbrances.<br/><br/>
        
        <b>2. TRADEMARKS</b><br/><br/>
        
        StartupXYZ owns 3 registered trademarks:<br/>
        - "StartupXYZ" (word mark)<br/>
        - StartupXYZ logo (design mark)<br/>
        - "IntelliFlow" (product name)<br/><br/>
        
        <b>3. TRADE SECRETS</b><br/><br/>
        
        We have reviewed StartupXYZ's trade secret protection protocols. All employees have 
        signed appropriate NDAs. See <b>Document: Non-Disclosure Agreement</b> template.<br/><br/>
        
        <b>4. THIRD-PARTY IP</b><br/><br/>
        
        StartupXYZ uses 47 open-source libraries. License compliance verified - no copyleft 
        contamination issues identified.<br/><br/>
        
        <b>5. PENDING MATTERS</b><br/><br/>
        
        There is one pending patent application (Application No. 17/456,789) for "Advanced 
        Federated Learning System" expected to issue Q2 2025. This is noted in 
        <b>Document: Risk Assessment Memo</b> as a minor risk item.<br/><br/>
        
        <b>6. LITIGATION</b><br/><br/>
        
        No IP-related litigation is pending or threatened. This is confirmed in 
        <b>Document: Legal Opinion Letter</b>.<br/><br/>
        
        This certification is provided in connection with the due diligence process and 
        may be relied upon by TechCorp Industries, Inc.<br/><br/>
        
        Sincerely,<br/>
        PatentWatch Legal Services<br/>
        By: Robert Kim, Patent Attorney
        """
    },
    
    "04_risk_assessment.pdf": {
        "title": "RISK ASSESSMENT MEMO",
        "content": """
        <b>CONFIDENTIAL RISK ASSESSMENT MEMORANDUM</b><br/><br/>
        
        <b>To:</b> TechCorp Board of Directors<br/>
        <b>From:</b> Corporate Development Team<br/>
        <b>Date:</b> December 22, 2024<br/>
        <b>Re:</b> Risk Assessment - StartupXYZ Acquisition<br/><br/>
        
        This memo summarizes key risks identified in connection with the proposed acquisition 
        as documented in the <b>Document: Acquisition Agreement</b>.<br/><br/>
        
        <b>1. HIGH-PRIORITY RISKS</b><br/><br/>
        
        <b>1.1 Customer Concentration (HIGH)</b><br/>
        - MegaCorp represents 28% of StartupXYZ revenue<br/>
        - MegaCorp contract contains change-of-control clause<br/>
        - Mitigation: Obtain consent prior to closing (see <b>Document: Customer Consent Letters</b>)<br/>
        - Impact if materialized: $3.4M annual revenue at risk<br/><br/>
        
        <b>1.2 Key Employee Retention (HIGH)</b><br/>
        - 5 senior engineers critical to product development<br/>
        - 2 have expressed interest in leaving post-acquisition<br/>
        - Mitigation: Retention packages per <b>Schedule 3 - Employee Transition Plan</b><br/>
        - Estimated cost: $2.5M in retention bonuses<br/><br/>
        
        <b>2. MEDIUM-PRIORITY RISKS</b><br/><br/>
        
        <b>2.1 Earnout Structure (MEDIUM)</b><br/>
        - $5M earnout tied to 2025-2026 performance metrics<br/>
        - Metrics defined in <b>Exhibit C - Earnout Terms</b> of the Acquisition Agreement<br/>
        - Risk: Disagreement on metric calculation methodology<br/>
        - Mitigation: Clear definitions in agreement; third-party arbitration clause<br/><br/>
        
        <b>2.2 Integration Costs (MEDIUM)</b><br/>
        - Estimated integration costs: $4.2M over 18 months<br/>
        - Systems integration detailed in <b>Document: Integration Plan</b><br/>
        - Risk: Cost overruns of 20-30% typical in tech acquisitions<br/><br/>
        
        <b>3. LOW-PRIORITY RISKS</b><br/><br/>
        
        <b>3.1 Pending Patent Application (LOW)</b><br/>
        - One patent pending as noted in <b>Document: IP Certification Letter</b><br/>
        - Low risk of rejection based on patent attorney's assessment<br/><br/>
        
        <b>3.2 Regulatory Approval (LOW)</b><br/>
        - HSR filing required but expected to clear without issues<br/>
        - Timeline in <b>Document: Regulatory Approval Letter</b><br/><br/>
        
        <b>4. FINANCIAL IMPACT SUMMARY</b><br/><br/>
        
        Total risk-adjusted impact: $6.2M - $8.7M<br/>
        This is reflected in purchase price negotiations per <b>Document: Financial Adjustments Memo</b><br/><br/>
        
        <b>5. RECOMMENDATION</b><br/><br/>
        
        Despite identified risks, we recommend proceeding with the acquisition. The strategic 
        value of StartupXYZ's AI technology platform justifies the purchase price when 
        accounting for risk mitigation costs. All findings are consistent with 
        <b>Document: Due Diligence Report</b>.<br/><br/>
        
        <b>6. NEXT STEPS</b><br/><br/>
        
        - Finalize customer consent process<br/>
        - Execute retention agreements<br/>
        - Complete regulatory filings<br/>
        - Prepare for closing per <b>Document: Closing Checklist</b>
        """
    },
    
    "05_financial_adjustments.pdf": {
        "title": "FINANCIAL ADJUSTMENTS MEMO",
        "content": """
        <b>FINANCIAL ADJUSTMENTS MEMORANDUM</b><br/><br/>
        
        <b>To:</b> Deal Team<br/>
        <b>From:</b> Finance Department<br/>
        <b>Date:</b> December 23, 2024<br/>
        <b>Re:</b> Purchase Price Adjustments - StartupXYZ Acquisition<br/><br/>
        
        Following our review in connection with the <b>Document: Due Diligence Report</b>, 
        we recommend the following adjustments to the purchase price as set forth in 
        <b>Exhibit A - Financial Terms</b> of the <b>Document: Acquisition Agreement</b>.<br/><br/>
        
        <b>1. WORKING CAPITAL ADJUSTMENT</b><br/><br/>
        
        Target working capital: $1,200,000<br/>
        Estimated closing working capital: $980,000<br/>
        Adjustment: ($220,000)<br/><br/>
        
        <b>2. DEBT ADJUSTMENT</b><br/><br/>
        
        Previously disclosed debt: $1,500,000<br/>
        Additional identified debt: $175,000 (capital lease obligations)<br/>
        Adjustment: ($175,000)<br/><br/>
        
        <b>3. REVENUE RECOGNITION ADJUSTMENT</b><br/><br/>
        
        Deferred revenue requiring restatement: $340,000<br/>
        Impact on EBITDA: ($85,000)<br/>
        Implied value adjustment (at 15x): ($1,275,000)<br/><br/>
        
        <b>4. CONTINGENT LIABILITY RESERVE</b><br/><br/>
        
        As noted in <b>Document: Risk Assessment Memo</b>, we recommend establishing 
        reserves for:<br/>
        - Customer concentration risk: $500,000<br/>
        - Integration contingency: $800,000<br/>
        Total reserve: $1,300,000 (to be held in escrow per <b>Exhibit C - Earnout Terms</b>)<br/><br/>
        
        <b>5. SUMMARY OF ADJUSTMENTS</b><br/><br/>
        
        Original Purchase Price: $45,000,000<br/>
        Working Capital Adjustment: ($220,000)<br/>
        Debt Adjustment: ($175,000)<br/>
        Revenue Recognition: ($1,275,000)<br/>
        <b>Adjusted Purchase Price: $43,330,000</b><br/><br/>
        
        Plus escrow reserve: $1,300,000<br/>
        <b>Total Cash Required at Closing: $44,630,000</b><br/><br/>
        
        <b>6. PAYMENT STRUCTURE</b><br/><br/>
        
        As revised from <b>Document: Acquisition Agreement</b> Section 2.2:<br/>
        (a) Cash at closing: $28,330,000 (adjusted)<br/>
        (b) Stock consideration: $10,000,000 (per <b>Exhibit B - Stock Valuation</b>)<br/>
        (c) Earnout: $5,000,000 (unchanged, per <b>Exhibit C - Earnout Terms</b>)<br/>
        (d) Escrow: $1,300,000 (18-month release schedule)<br/><br/>
        
        These adjustments have been discussed with Seller's representatives and are 
        subject to final negotiation.<br/><br/>
        
        Please refer to <b>Document: Closing Checklist</b> for timeline and requirements.
        """
    },
    
    "06_legal_opinion.pdf": {
        "title": "LEGAL OPINION LETTER",
        "content": """
        <b>LEGAL OPINION LETTER</b><br/><br/>
        
        <b>Date:</b> December 18, 2024<br/><br/>
        
        TechCorp Industries, Inc.<br/>
        500 Technology Drive<br/>
        San Francisco, CA 94105<br/><br/>
        
        <b>Re: Acquisition of StartupXYZ LLC</b><br/><br/>
        
        Ladies and Gentlemen:<br/><br/>
        
        We have acted as legal counsel to StartupXYZ LLC ("Company") in connection with 
        the proposed acquisition by TechCorp Industries, Inc. pursuant to the 
        <b>Document: Acquisition Agreement</b> dated January 15, 2025.<br/><br/>
        
        <b>DOCUMENTS REVIEWED</b><br/><br/>
        
        In connection with this opinion, we have reviewed:<br/>
        1. The Acquisition Agreement and all Exhibits and Schedules<br/>
        2. <b>Document: Due Diligence Report</b> prepared by Morrison & Associates<br/>
        3. <b>Document: IP Certification Letter</b> from PatentWatch Legal Services<br/>
        4. All material contracts listed in <b>Schedule 2 - Material Contracts</b><br/>
        5. Corporate records and organizational documents of the Company<br/>
        6. <b>Document: Non-Disclosure Agreement</b> between the parties<br/><br/>
        
        <b>OPINIONS</b><br/><br/>
        
        Based on our review, we are of the opinion that:<br/><br/>
        
        <b>1. Corporate Status</b><br/>
        The Company is a limited liability company duly organized, validly existing, and 
        in good standing under the laws of Delaware.<br/><br/>
        
        <b>2. Authority</b><br/>
        The Company has full power and authority to execute and deliver the Acquisition 
        Agreement and to consummate the transactions contemplated thereby.<br/><br/>
        
        <b>3. No Conflicts</b><br/>
        The execution and delivery of the Acquisition Agreement does not violate any 
        provision of the Company's organizational documents or any material contract, 
        except for change-of-control provisions noted in <b>Document: Customer Consent Letters</b>.<br/><br/>
        
        <b>4. Litigation</b><br/>
        There is no litigation, arbitration, or governmental proceeding pending or, to 
        our knowledge, threatened against the Company that would have a material adverse 
        effect on the Company or the transactions contemplated by the Acquisition Agreement.<br/><br/>
        
        This opinion confirms the representations in the <b>Document: IP Certification Letter</b> 
        regarding absence of IP litigation.<br/><br/>
        
        <b>5. Regulatory Compliance</b><br/>
        The Company is in material compliance with all applicable laws and regulations. 
        The HSR filing requirements are addressed in <b>Document: Regulatory Approval Letter</b>.<br/><br/>
        
        <b>QUALIFICATIONS</b><br/><br/>
        
        This opinion is subject to the following qualifications:<br/>
        1. We express no opinion on tax matters (see separate tax opinion)<br/>
        2. This opinion is limited to Delaware and federal law<br/>
        3. Certain contracts require third-party consents as noted above<br/><br/>
        
        This opinion is provided solely for your benefit in connection with the 
        transactions contemplated by the Acquisition Agreement.<br/><br/>
        
        Very truly yours,<br/>
        Wilson & Partners LLP<br/>
        By: Jennifer Walsh, Partner
        """
    },
    
    "07_nda.pdf": {
        "title": "NON-DISCLOSURE AGREEMENT",
        "content": """
        <b>MUTUAL NON-DISCLOSURE AGREEMENT</b><br/><br/>
        
        This Mutual Non-Disclosure Agreement ("NDA") is entered into as of October 1, 2024, 
        by and between:<br/><br/>
        
        <b>TechCorp Industries, Inc.</b> ("TechCorp")<br/>
        500 Technology Drive, San Francisco, CA 94105<br/><br/>
        
        and<br/><br/>
        
        <b>StartupXYZ LLC</b> ("StartupXYZ")<br/>
        123 Innovation Way, Palo Alto, CA 94301<br/><br/>
        
        (each a "Party" and collectively the "Parties")<br/><br/>
        
        <b>RECITALS</b><br/><br/>
        
        The Parties wish to explore a potential business relationship, including a possible 
        acquisition of StartupXYZ by TechCorp (the "Purpose"), which is now documented in 
        the <b>Document: Acquisition Agreement</b>.<br/><br/>
        
        <b>1. DEFINITION OF CONFIDENTIAL INFORMATION</b><br/><br/>
        
        "Confidential Information" means any non-public information disclosed by either 
        Party, including but not limited to:<br/>
        - Financial information (as contained in <b>Document: Due Diligence Report</b>)<br/>
        - Technical information (as certified in <b>Document: IP Certification Letter</b>)<br/>
        - Business strategies and plans<br/>
        - Customer and supplier information<br/>
        - Employee information (as detailed in <b>Schedule 3 - Employee Transition Plan</b>)<br/><br/>
        
        <b>2. OBLIGATIONS</b><br/><br/>
        
        Each Party agrees to:<br/>
        (a) Hold Confidential Information in strict confidence<br/>
        (b) Not disclose Confidential Information to third parties without prior written consent<br/>
        (c) Use Confidential Information solely for the Purpose<br/>
        (d) Limit access to Confidential Information to employees with a need to know<br/><br/>
        
        <b>3. TERM</b><br/><br/>
        
        This NDA shall remain in effect for three (3) years from the date first written 
        above, or until superseded by the confidentiality provisions in the 
        <b>Document: Acquisition Agreement</b> Article V.<br/><br/>
        
        <b>4. EXCLUSIONS</b><br/><br/>
        
        Confidential Information does not include information that:<br/>
        (a) Is or becomes publicly available through no fault of the receiving Party<br/>
        (b) Was rightfully in the receiving Party's possession prior to disclosure<br/>
        (c) Is rightfully obtained from a third party without restriction<br/>
        (d) Is independently developed without use of Confidential Information<br/><br/>
        
        <b>5. RETURN OF MATERIALS</b><br/><br/>
        
        Upon request or termination, each Party shall return or destroy all Confidential 
        Information, except as required for legal or regulatory purposes.<br/><br/>
        
        <b>6. NO LICENSE</b><br/><br/>
        
        Nothing in this NDA grants any rights to intellectual property, except as 
        subsequently agreed in the <b>Document: Acquisition Agreement</b> and 
        <b>Schedule 1 - IP Assets</b>.<br/><br/>
        
        IN WITNESS WHEREOF, the Parties have executed this NDA as of the date first above written.<br/><br/>
        
        TechCorp Industries, Inc.<br/>
        By: ______________________<br/>
        Name: James Mitchell<br/>
        Title: CEO<br/><br/>
        
        StartupXYZ LLC<br/>
        By: ______________________<br/>
        Name: Sarah Chen<br/>
        Title: Founder & CEO
        """
    },
    
    "08_regulatory_approval.pdf": {
        "title": "REGULATORY APPROVAL LETTER",
        "content": """
        <b>FEDERAL TRADE COMMISSION</b><br/>
        <b>PREMERGER NOTIFICATION OFFICE</b><br/><br/>
        
        January 28, 2025<br/><br/>
        
        TechCorp Industries, Inc.<br/>
        500 Technology Drive<br/>
        San Francisco, CA 94105<br/><br/>
        
        StartupXYZ LLC<br/>
        123 Innovation Way<br/>
        Palo Alto, CA 94301<br/><br/>
        
        <b>Re: Early Termination of HSR Waiting Period</b><br/>
        <b>Transaction: Acquisition of StartupXYZ LLC by TechCorp Industries, Inc.</b><br/><br/>
        
        Dear Parties:<br/><br/>
        
        This letter confirms that the Federal Trade Commission has granted early 
        termination of the waiting period under the Hart-Scott-Rodino Antitrust 
        Improvements Act of 1976 for the above-referenced transaction.<br/><br/>
        
        <b>FILING DETAILS</b><br/><br/>
        
        Filing Date: January 10, 2025<br/>
        Transaction Value: $45,000,000 (as stated in <b>Document: Acquisition Agreement</b>)<br/>
        HSR Filing Fee: $30,000<br/>
        Early Termination Granted: January 28, 2025<br/><br/>
        
        <b>EFFECT OF EARLY TERMINATION</b><br/><br/>
        
        The parties may now consummate the transaction at any time. This early termination 
        satisfies the condition precedent set forth in Article IV, Section 4.1(a) of the 
        <b>Document: Acquisition Agreement</b>.<br/><br/>
        
        Please note that early termination of the waiting period does not preclude the 
        Commission from taking any action it deems necessary to protect competition.<br/><br/>
        
        <b>NEXT STEPS</b><br/><br/>
        
        Per the <b>Document: Closing Checklist</b>, you may now proceed with the closing 
        scheduled for March 1, 2025, subject to satisfaction of other conditions in the 
        <b>Document: Acquisition Agreement</b>.<br/><br/>
        
        The <b>Document: Risk Assessment Memo</b> correctly identified this as a low-risk 
        item. The market analysis in the <b>Document: Due Diligence Report</b> supported 
        the determination that this transaction does not raise competitive concerns.<br/><br/>
        
        Sincerely,<br/>
        Premerger Notification Office<br/>
        Federal Trade Commission
        """
    },
    
    "09_customer_consents.pdf": {
        "title": "CUSTOMER CONSENT LETTERS",
        "content": """
        <b>CUSTOMER CONSENT STATUS REPORT</b><br/><br/>
        
        <b>Date:</b> February 15, 2025<br/>
        <b>To:</b> Deal Team<br/>
        <b>From:</b> Legal Department<br/>
        <b>Re:</b> Change of Control Consent Status<br/><br/>
        
        As required by <b>Schedule 2 - Material Contracts</b> of the 
        <b>Document: Acquisition Agreement</b>, this memo summarizes the status of 
        customer consents for contracts containing change-of-control provisions.<br/><br/>
        
        <b>CONSENT STATUS SUMMARY</b><br/><br/>
        
        <b>1. MegaCorp Inc. - OBTAINED</b><br/>
        Contract Value: $3.4M annual<br/>
        Consent Received: February 10, 2025<br/>
        Notes: MegaCorp requested meeting with TechCorp leadership; meeting held 2/8/25. 
        Consent granted with no additional conditions. This addresses the primary concern 
        noted in <b>Document: Risk Assessment Memo</b> Section 1.1.<br/><br/>
        
        <b>2. DataFlow Systems - OBTAINED</b><br/>
        Contract Value: $1.2M annual<br/>
        Consent Received: February 5, 2025<br/>
        Notes: Standard consent process. No concerns raised.<br/><br/>
        
        <b>3. CloudTech Partners - PENDING</b><br/>
        Contract Value: $890K annual<br/>
        Status: Consent requested February 1, 2025<br/>
        Expected: February 20, 2025<br/>
        Notes: Legal review in progress at CloudTech. Their counsel has reviewed the 
        <b>Document: Acquisition Agreement</b> and has no objections. Verbal confirmation 
        received; written consent expected shortly.<br/><br/>
        
        <b>IMPACT ANALYSIS</b><br/><br/>
        
        Per <b>Document: Due Diligence Report</b> Section 4, there were 3 contracts 
        requiring consent:<br/>
        - 2 obtained (representing $4.6M annual revenue)<br/>
        - 1 pending (representing $890K annual revenue)<br/><br/>
        
        <b>CLOSING IMPLICATIONS</b><br/><br/>
        
        The <b>Document: Acquisition Agreement</b> Article IV requires "material" customer 
        consents as a closing condition. With MegaCorp consent obtained, this condition 
        is substantially satisfied. The pending CloudTech consent is expected before 
        the March 1 closing date per <b>Document: Closing Checklist</b>.<br/><br/>
        
        <b>ATTACHMENTS</b><br/><br/>
        
        Attached hereto:<br/>
        - Exhibit A: MegaCorp Consent Letter (dated February 10, 2025)<br/>
        - Exhibit B: DataFlow Systems Consent Letter (dated February 5, 2025)<br/>
        - Exhibit C: CloudTech Partners Draft Consent (pending signature)<br/><br/>
        
        <b>RECOMMENDATION</b><br/><br/>
        
        We recommend proceeding with closing preparations. The risk of CloudTech 
        withholding consent is low based on discussions with their counsel. This 
        is consistent with the risk mitigation strategy in <b>Document: Risk Assessment Memo</b>.
        """
    },
    
    "10_closing_checklist.pdf": {
        "title": "CLOSING CHECKLIST",
        "content": """
        <b>CLOSING CHECKLIST</b><br/>
        <b>Acquisition of StartupXYZ LLC by TechCorp Industries, Inc.</b><br/><br/>
        
        <b>Closing Date:</b> March 1, 2025<br/>
        <b>Closing Location:</b> Wilson & Partners LLP, San Francisco<br/><br/>
        
        <b>I. PRE-CLOSING CONDITIONS</b><br/><br/>
        
        <b>A. Regulatory</b><br/>
        [X] HSR Filing submitted - <b>Document: Regulatory Approval Letter</b><br/>
        [X] Early termination received (January 28, 2025)<br/>
        [ ] State regulatory filings (if required)<br/><br/>
        
        <b>B. Third-Party Consents</b><br/>
        [X] MegaCorp consent - <b>Document: Customer Consent Letters</b><br/>
        [X] DataFlow consent - <b>Document: Customer Consent Letters</b><br/>
        [ ] CloudTech consent (expected February 20) - <b>Document: Customer Consent Letters</b><br/><br/>
        
        <b>C. Due Diligence Completion</b><br/>
        [X] Financial due diligence - <b>Document: Due Diligence Report</b><br/>
        [X] Legal due diligence - <b>Document: Legal Opinion Letter</b><br/>
        [X] IP due diligence - <b>Document: IP Certification Letter</b><br/>
        [X] Risk assessment - <b>Document: Risk Assessment Memo</b><br/><br/>
        
        <b>II. CLOSING DOCUMENTS</b><br/><br/>
        
        <b>A. Transaction Documents</b><br/>
        [ ] Executed <b>Document: Acquisition Agreement</b><br/>
        [ ] Bill of Sale<br/>
        [ ] Assignment and Assumption Agreement<br/>
        [ ] IP Assignment Agreement (per <b>Schedule 1 - IP Assets</b>)<br/><br/>
        
        <b>B. Corporate Documents</b><br/>
        [ ] Seller's Certificate of Good Standing<br/>
        [ ] Secretary's Certificate (resolutions, incumbency)<br/>
        [ ] Buyer's Certificate of Good Standing<br/><br/>
        
        <b>C. Financial Documents</b><br/>
        [ ] Closing Statement per <b>Document: Financial Adjustments Memo</b><br/>
        [ ] Wire transfer instructions<br/>
        [ ] Escrow Agreement (per <b>Exhibit C - Earnout Terms</b>)<br/>
        [ ] Stock certificates or book entry (per <b>Exhibit B - Stock Valuation</b>)<br/><br/>
        
        <b>D. Employment Documents</b><br/>
        [ ] Retention agreements per <b>Schedule 3 - Employee Transition Plan</b><br/>
        [ ] Offer letters for key employees<br/>
        [ ] WARN Act compliance (if applicable)<br/><br/>
        
        <b>III. CLOSING FUNDS</b><br/><br/>
        
        Per <b>Document: Financial Adjustments Memo</b>:<br/>
        [ ] Cash payment: $28,330,000<br/>
        [ ] Escrow deposit: $1,300,000<br/>
        [ ] Stock issuance: $10,000,000<br/>
        Total at Closing: $39,630,000<br/><br/>
        
        <b>IV. POST-CLOSING</b><br/><br/>
        
        [ ] File UCC termination statements<br/>
        [ ] Update corporate records<br/>
        [ ] Integration kickoff per <b>Document: Integration Plan</b><br/>
        [ ] Employee communications<br/>
        [ ] Customer notifications<br/>
        [ ] Press release<br/><br/>
        
        <b>V. RESPONSIBLE PARTIES</b><br/><br/>
        
        Buyer's Counsel: Morrison & Associates LLP<br/>
        Seller's Counsel: Wilson & Partners LLP<br/>
        Escrow Agent: First National Trust<br/><br/>
        
        <b>VI. KEY CONTACTS</b><br/><br/>
        
        TechCorp: James Mitchell (CEO), (415) 555-0100<br/>
        StartupXYZ: Sarah Chen (CEO), (650) 555-0200<br/>
        Legal (Buyer): John Morrison, (415) 555-0300<br/>
        Legal (Seller): Jennifer Walsh, (415) 555-0400
        """
    }
}


def create_pdf(filename: str, title: str, content: str):
    """Create a PDF document."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    doc = SimpleDocTemplate(filepath, pagesize=letter,
                           topMargin=1*inch, bottomMargin=1*inch,
                           leftMargin=1*inch, rightMargin=1*inch)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=1  # Center
    )
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        spaceAfter=12
    )
    
    story = []
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.5*inch))
    
    # Split content into paragraphs and add them
    paragraphs = content.strip().split('<br/><br/>')
    for para in paragraphs:
        para = para.replace('<br/>', '<br/>')
        story.append(Paragraph(para, body_style))
    
    doc.build(story)
    print(f"Created: {filepath}")


def main():
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print(f"\nGenerating {len(DOCUMENTS)} test documents in {OUTPUT_DIR}/\n")
    
    for filename, doc_info in DOCUMENTS.items():
        create_pdf(filename, doc_info["title"], doc_info["content"])
    
    print(f"\n✅ Generated {len(DOCUMENTS)} documents successfully!")
    print(f"\nDocument cross-reference map:")
    print("=" * 60)
    print("""
    Acquisition Agreement (01)
    ├── references: Exhibit A, B, C, Schedule 1-3
    ├── referenced by: ALL other documents
    │
    Due Diligence Report (02)
    ├── references: Acquisition Agreement, IP Cert, Risk Assessment
    ├── referenced by: Legal Opinion, Risk Assessment, Regulatory
    │
    IP Certification (03)
    ├── references: Acquisition Agreement, Schedule 1, NDA
    ├── referenced by: Due Diligence, Legal Opinion
    │
    Risk Assessment (04)
    ├── references: Acquisition Agreement, Due Diligence, IP Cert
    ├── referenced by: Financial Adjustments, Customer Consents
    │
    Financial Adjustments (05)
    ├── references: Due Diligence, Risk Assessment, Acquisition Agreement
    ├── referenced by: Closing Checklist
    │
    Legal Opinion (06)
    ├── references: Acquisition Agreement, Due Diligence, IP Cert, NDA
    ├── referenced by: Closing Checklist
    │
    NDA (07)
    ├── references: Acquisition Agreement, Due Diligence, IP Cert
    ├── referenced by: IP Cert, Legal Opinion
    │
    Regulatory Approval (08)
    ├── references: Acquisition Agreement, Due Diligence, Risk Assessment
    ├── referenced by: Closing Checklist
    │
    Customer Consents (09)
    ├── references: Acquisition Agreement, Risk Assessment, Schedule 2
    ├── referenced by: Closing Checklist
    │
    Closing Checklist (10)
    └── references: ALL documents
    """)


if __name__ == "__main__":
    main()

