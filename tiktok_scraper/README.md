# TikTok Shop Scraper - Extractor Module

This module extracts key product fields from TikTok Shop product detail pages (`sample_product.html`).

## Project Structure

tiktok-shop-scraper/
├── tiktok_scraper/
│ └── extractor/
│ ├── extractor.py
│ └── sample_product.html # (Not committed. See below.)
├── requirements.txt
└── README.md

## Setup Instructions

### 1. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Save Sample HTML File

The test file sample_product.html is not included in the repo.

Please manually save a TikTok Shop product page in your browser:

Right-click the product detail page > Save Page As… > Save as HTML only

Rename and move the file to:

```bash
tiktok_scraper/extractor/sample_product.html
```

### 4. Run Extractor

```bash
python tiktok_scraper/extractor/extractor.py
```
