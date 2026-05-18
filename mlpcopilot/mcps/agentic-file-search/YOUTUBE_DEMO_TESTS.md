# YouTube Demo: FS-Explorer Test Results

## System Overview

- **25 PDF documents** (~93 pages total)
- **63 cross-references** between documents
- **Parallel document scanning** using ThreadPoolExecutor
- **Three-phase exploration**: Scan → Filter → Deep Dive + Backtracking

---

## Test Results Summary

| Test | Question | Docs Parsed | Tokens Used | Cost | Time |
|------|----------|-------------|-------------|------|------|
| 1 | CTO & retention bonus | 1 | 27,376 | $0.0021 | ~30s |
| 2 | Litigation & insurance | 2 | 41,431 | $0.0033 | ~30s |
| 3 | Patents owned | 1 | 27,416 | $0.0022 | ~27s |

---

## TEST 1: Simple Fact Lookup ✅

**Question:**
```bash
uv run explore --task "Look in data/large_acquisition/. Who is the CTO and what is their retention bonus?"
```

**Agent Answer:**
> Dr. Sarah Chen is the CTO and their retention bonus is $1,200,000.

**Verification (from 07_employee_schedule.pdf):**
```
1. Dr. Sarah Chen - CTO - 15 years experience - Retention bonus: $1,200,000
```

| Metric | Value |
|--------|-------|
| Documents Scanned | 26 (parallel) |
| Documents Parsed | 1 |
| Tokens Used | 27,376 |
| Cost | $0.0021 |
| ✅ Accuracy | **100% Correct** |

---

## TEST 2: Cross-Reference Following ✅

**Question:**
```bash
uv run explore --task "Look in data/large_acquisition/. What is the total litigation exposure and is it covered by insurance?"
```

**Agent Answer:**
> The total litigation exposure is between $650,000 and $2,350,000. The Smith v. InnovateTech Solutions, Inc. case, with an exposure of $150,000 - $350,000, is covered by insurance. The DataTech LLC v. InnovateTech Solutions, Inc. case, with an exposure of $500,000 - $2,000,000, does not specify if it is covered by insurance.

**Verification (from 12_litigation_schedule.pdf):**
```
1. Smith v. InnovateTech Solutions, Inc.
   Exposure: $150,000 - $350,000 (covered by insurance)

2. DataTech LLC v. InnovateTech Solutions, Inc.
   Exposure: Preliminary assessment $500,000 - $2,000,000
```

**Cross-Reference Followed:**
- Agent noticed reference to "Legal Opinion Letter" 
- Parsed `24_legal_opinion.pdf` to get complete picture

| Metric | Value |
|--------|-------|
| Documents Scanned | 26 (parallel) |
| Documents Parsed | 2 (litigation + legal opinion) |
| Tokens Used | 41,431 |
| Cost | $0.0033 |
| ✅ Accuracy | **100% Correct** |

---

## TEST 3: Multi-Document IP Analysis ✅

**Question:**
```bash
uv run explore --task "Look in data/large_acquisition/. What patents does the company own and are there any pending applications?"
```

**Agent Answer:**
> The company owns the following patents: 
> - US Patent 10,123,456 - 'Machine Learning System for Predictive Analytics' - Issued 2021
> - US Patent 10,234,567 - 'Distributed Data Processing Architecture' - Issued 2022
> - US Patent 10,345,678 - 'Real-time Anomaly Detection Method' - Issued 2023
> 
> There is one pending application: US Application 17/456,789 - 'Automated Workflow Optimization' - Filed 2024.

**Verification (from 06_ip_schedule.pdf):**
```
US Patent 10,123,456 - 'Machine Learning System for Predictive Analytics' - Issued 2021
US Patent 10,234,567 - 'Distributed Data Processing Architecture' - Issued 2022
US Patent 10,345,678 - 'Real-time Anomaly Detection Method' - Issued 2023
Pending: US Application 17/456,789 - 'Automated Workflow Optimization' - Filed 2024
```

| Metric | Value |
|--------|-------|
| Documents Scanned | 26 (parallel) |
| Documents Parsed | 1 |
| Tokens Used | 27,416 |
| Cost | $0.0022 |
| ✅ Accuracy | **100% Correct** |

---

## Additional Demo Tests

### Purchase Price & Payment Structure
```bash
uv run explore --task "Look in data/large_acquisition/. What is the total purchase price and how is it being paid?"
```
**Expected:** $125M total ($80M cash + $30M stock + $15M escrow)

### Closing Conditions Status
```bash
uv run explore --task "Look in data/large_acquisition/. What are all the conditions that must be satisfied before closing and what is the status of each?"
```
**Expected:** HSR ✅, State filings ✅, MegaCorp consent ✅, GlobalBank pending, Employee retention ✅, Legal opinion ✅, Good standing ordered

### Key Employee Compensation
```bash
uv run explore --task "Look in data/large_acquisition/. List all the key employees and their retention bonuses"
```
**Expected:** 5 employees totaling $3.5M in retention bonuses

---

## Key Architecture Points to Highlight

### 1. Parallel Scanning (scan_folder)
- Scans ALL 26 documents simultaneously using ThreadPoolExecutor
- Takes ~25 seconds for entire folder
- Returns quick preview of each document

### 2. Smart Filtering
- LLM reviews all previews at once
- Identifies which documents are relevant
- Avoids parsing irrelevant documents

### 3. Cross-Reference Discovery
- Agent watches for document references like:
  - "See Document: Legal Opinion Letter"
  - "Per Document: Risk Assessment Memo"
- Automatically follows references (backtracking)

### 4. Document Caching
- Documents cached after first parse
- Backtracking is free (no re-parsing)

---

## Cost Analysis

| Scenario | Tokens | Est. Cost |
|----------|--------|-----------|
| Simple query (1 doc) | ~27K | $0.002 |
| Cross-ref query (2-3 docs) | ~40K | $0.003 |
| Complex synthesis (5+ docs) | ~60K | $0.005 |
| All 25 documents parsed | ~150K | $0.012 |

**Key Insight:** Even with 25 documents, costs are minimal because the system only parses what's needed!

---

## Commands to Run Demo

```bash
# Setup
cd /path/to/fs-explorer
export GOOGLE_API_KEY="your-key"

# Run any test
uv run explore --task "Look in data/large_acquisition/. [YOUR QUESTION]"
```

---

## What to Show in Video

1. **The folder scan** - Watch as 26 documents are scanned in parallel
2. **Smart filtering** - Note which documents the agent CHOOSES to parse
3. **Cross-reference following** - Show agent backtracking to referenced docs
4. **Token usage summary** - Highlight the efficiency stats at the end
5. **Verification** - Show the actual PDF content matches the answer

