# ReconcilePro

## GST Reconciliation & Anomaly Detection Platform

ReconcilePro is a web-based MSME GST reconciliation platform designed to automate the comparison of internal accounting records with GST return data and identify discrepancies that require review.

The project combines a React frontend, FastAPI backend, PostgreSQL/Supabase database, authentication, automated reconciliation, reporting, and an anomaly-detection framework.

---

## Project Overview

Manual GST reconciliation can involve comparing multiple records and identifying mismatches between internal books and GST filing data.

ReconcilePro provides a centralized workflow for:

- Sales Register ↔ GSTR-1 reconciliation
- Purchase Register ↔ GSTR-2A reconciliation
- GSTR-3B summary
- Tax-period filtering
- Duplicate invoice detection
- Missing and extra invoice detection
- Business-level data isolation
- CSV data ingestion
- Reports and exports
- Potential anomaly analysis
- Professional MSME compliance dashboard

---

## Key Features

### GST Reconciliation

The system compares internal records with GST-related records and classifies invoices as:

- `MATCH`
- `MISMATCH`
- `MISSING_IN_GST`
- `EXTRA_IN_GST`

The reconciliation process also calculates:

- Taxable value difference
- GST amount difference
- Reconciliation explanation
- Counterparty GSTIN information

### Database-Backed Processing

Reconciliation uses authenticated business data stored in PostgreSQL/Supabase.

```text
React Frontend
       ↓
FastAPI Backend
       ↓
Authentication
       ↓
Active Business
       ↓
Supabase PostgreSQL
       ↓
Reconciliation Engine
       ↓
Dashboard / Reports
