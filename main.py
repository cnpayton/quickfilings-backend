from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import asyncio
from typing import List, Optional
import re
from datetime import datetime, timedelta
import json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import time
import io

app = FastAPI(title="QuickFilings API", version="1.0.0")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class FileItem(BaseModel):
    name: str
    type: str
    date: str
    size: str
    url: str
    download_url: Optional[str] = None

class CompanyData(BaseModel):
    ticker: str
    name: str
    cik: str
    exchange: str

class SearchResponse(BaseModel):
    company: CompanyData
    files: List[FileItem]

# Company name mapping for common tickers
COMPANY_NAMES = {
    'AAPL': 'Apple Inc.',
    'MSFT': 'Microsoft Corporation',
    'GOOGL': 'Alphabet Inc.',
    'AMZN': 'Amazon.com Inc.',
    'TSLA': 'Tesla Inc.',
    'META': 'Meta Platforms Inc.',
    'NVDA': 'NVIDIA Corporation',
    'JPM': 'JPMorgan Chase & Co.',
    'JNJ': 'Johnson & Johnson',
    'V': 'Visa Inc.',
    'WMT': 'Walmart Inc.',
    'PG': 'Procter & Gamble Co.',
    'UNH': 'UnitedHealth Group Inc.',
    'HD': 'Home Depot Inc.',
    'MA': 'Mastercard Inc.',
    'BAC': 'Bank of America Corp.',
    'ABBV': 'AbbVie Inc.',
    'AVGO': 'Broadcom Inc.',
    'XOM': 'Exxon Mobil Corp.',
    'LLY': 'Eli Lilly and Co.',
    'PFE': 'Pfizer Inc.',
    'TMO': 'Thermo Fisher Scientific Inc.',
    'COST': 'Costco Wholesale Corp.',
    'DIS': 'Walt Disney Co.',
    'ABT': 'Abbott Laboratories',
    'CRM': 'Salesforce Inc.',
    'NFLX': 'Netflix Inc.',
    'ADBE': 'Adobe Inc.',
    'VZ': 'Verizon Communications Inc.',
    'NKE': 'Nike Inc.',
    'CMCSA': 'Comcast Corp.',
    'PEP': 'PepsiCo Inc.',
    'T': 'AT&T Inc.',
    'ORCL': 'Oracle Corp.',
    'KO': 'Coca-Cola Co.',
    'INTC': 'Intel Corp.',
    'CVX': 'Chevron Corp.',
    'MRK': 'Merck & Co. Inc.',
    'CSCO': 'Cisco Systems Inc.',
    'ACN': 'Accenture PLC',
    'BMY': 'Bristol-Myers Squibb Co.',
    'MDT': 'Medtronic PLC',
    'WFC': 'Wells Fargo & Co.',
    'TXN': 'Texas Instruments Inc.',
    'RTX': 'Raytheon Technologies Corp.',
    'HON': 'Honeywell International Inc.',
    'QCOM': 'Qualcomm Inc.',
    'UPS': 'United Parcel Service Inc.',
    'LOW': 'Lowe\'s Companies Inc.',
    'LIN': 'Linde PLC',
    'PM': 'Philip Morris International Inc.',
    'SBUX': 'Starbucks Corp.',
    'CAT': 'Caterpillar Inc.',
    'GS': 'Goldman Sachs Group Inc.',
    'MS': 'Morgan Stanley',
    'IBM': 'International Business Machines Corp.',
    'GILD': 'Gilead Sciences Inc.',
    'CVS': 'CVS Health Corp.',
    'BLK': 'BlackRock Inc.',
    'AXP': 'American Express Co.',
    'ISRG': 'Intuitive Surgical Inc.',
    'DE': 'Deere & Co.',
    'AMAT': 'Applied Materials Inc.',
    'ADI': 'Analog Devices Inc.',
    'MMM': '3M Co.',
    'PYPL': 'PayPal Holdings Inc.',
    'LRCX': 'Lam Research Corp.',
    'BA': 'Boeing Co.',
    'MU': 'Micron Technology Inc.',
    'TJX': 'TJX Companies Inc.',
    'BKNG': 'Booking Holdings Inc.',
    'MDLZ': 'Mondelez International Inc.',
    'REGN': 'Regeneron Pharmaceuticals Inc.',
    'ZTS': 'Zoetis Inc.',
    'C': 'Citigroup Inc.',
    'CCI': 'Crown Castle Inc.',
    'TMUS': 'T-Mobile US Inc.',
    'PLD': 'Prologis Inc.',
    'SO': 'Southern Co.',
    'CB': 'Chubb Ltd.',
    'SYK': 'Stryker Corp.',
    'NOW': 'ServiceNow Inc.',
    'DUK': 'Duke Energy Corp.',
    'BSX': 'Boston Scientific Corp.',
    'BDX': 'Becton Dickinson and Co.',
    'MO': 'Altria Group Inc.',
    'AMT': 'American Tower Corp.',
    'EQIX': 'Equinix Inc.',
    'CSX': 'CSX Corp.',
    'USB': 'U.S. Bancorp',
    'ICE': 'Intercontinental Exchange Inc.',
    'AON': 'Aon PLC',
    'CL': 'Colgate-Palmolive Co.',
    'NSC': 'Norfolk Southern Corp.',
    'FDX': 'FedEx Corp.',
    'SHW': 'Sherwin-Williams Co.',
    'ITW': 'Illinois Tool Works Inc.',
    'GD': 'General Dynamics Corp.',
    'FCX': 'Freeport-McMoRan Inc.',
    'CME': 'CME Group Inc.',
    'INTU': 'Intuit Inc.',
    'TGT': 'Target Corp.',
    'PNC': 'PNC Financial Services Group Inc.',
    'SCHW': 'Charles Schwab Corp.',
    'EOG': 'EOG Resources Inc.',
    'EMR': 'Emerson Electric Co.',
    'MCO': 'Moody\'s Corp.',
    'NOC': 'Northrop Grumman Corp.',
    'MPC': 'Marathon Petroleum Corp.',
    'APD': 'Air Products and Chemicals Inc.',
    'KLAC': 'KLA Corp.',
    'SPGI': 'S&P Global Inc.',
    'SNPS': 'Synopsys Inc.',
    'CDNS': 'Cadence Design Systems Inc.',
    'MMC': 'Marsh & McLennan Companies Inc.',
    'TFC': 'Truist Financial Corp.',
    'ADP': 'Automatic Data Processing Inc.',
    'ORLY': 'O\'Reilly Automotive Inc.',
    'COP': 'ConocoPhillips',
    'ECL': 'Ecolab Inc.',
    'GM': 'General Motors Co.',
    'PSX': 'Phillips 66',
    'VLO': 'Valero Energy Corp.',
    'NEM': 'Newmont Corp.',
    'CARR': 'Carrier Global Corp.',
    'SLB': 'Schlumberger Ltd.',
    'MNST': 'Monster Beverage Corp.',
    'WM': 'Waste Management Inc.',
    'GE': 'General Electric Co.',
    'ADSK': 'Autodesk Inc.',
    'MSI': 'Motorola Solutions Inc.',
    'AIG': 'American International Group Inc.',
    'NXPI': 'NXP Semiconductors NV',
    'PSA': 'Public Storage',
    'D': 'Dominion Energy Inc.',
    'ROST': 'Ross Stores Inc.',
    'MCHP': 'Microchip Technology Inc.',
    'PAYX': 'Paychex Inc.',
    'HUM': 'Humana Inc.',
    'O': 'Realty Income Corp.',
    'BK': 'Bank of New York Mellon Corp.',
    'SPG': 'Simon Property Group Inc.',
    'FAST': 'Fastenal Co.',
    'ODFL': 'Old Dominion Freight Line Inc.',
    'EXC': 'Exelon Corp.',
    'CTSH': 'Cognizant Technology Solutions Corp.',
    'KMB': 'Kimberly-Clark Corp.',
    'VRSK': 'Verisk Analytics Inc.',
    'CTAS': 'Cintas Corp.',
    'EA': 'Electronic Arts Inc.',
    'IDXX': 'IDEXX Laboratories Inc.',
    'VRTX': 'Vertex Pharmaceuticals Inc.',
    'YUM': 'Yum! Brands Inc.',
    'KHC': 'Kraft Heinz Co.',
    'BIIB': 'Biogen Inc.',
    'GIS': 'General Mills Inc.',
    'HSY': 'Hershey Co.',
    'EW': 'Edwards Lifesciences Corp.',
    'XEL': 'Xcel Energy Inc.',
    'CTVA': 'Corteva Inc.',
    'DLTR': 'Dollar Tree Inc.',
    'OTIS': 'Otis Worldwide Corp.',
    'WBA': 'Walgreens Boots Alliance Inc.',
    'HPQ': 'HP Inc.',
    'IQV': 'IQVIA Holdings Inc.',
    'ROK': 'Rockwell Automation Inc.',
    'MPWR': 'Monolithic Power Systems Inc.',
    'ENPH': 'Enphase Energy Inc.',
    'DXCM': 'DexCom Inc.',
    'FISV': 'Fiserv Inc.',
    'RMD': 'ResMed Inc.',
    'CPRT': 'Copart Inc.',
    'EXR': 'Extended Stay America Inc.',
    'CMG': 'Chipotle Mexican Grill Inc.',
    'WDC': 'Western Digital Corp.',
    'DHI': 'D.R. Horton Inc.',
    'LEN': 'Lennar Corp.',
    'ALGN': 'Align Technology Inc.',
    'FTV': 'Fortive Corp.',
    'KEYS': 'Keysight Technologies Inc.',
    'CEG': 'Constellation Energy Corp.',
    'ANSS': 'ANSYS Inc.',
    'ROP': 'Roper Technologies Inc.',
    'AWK': 'American Water Works Co. Inc.',
    'NTRS': 'Northern Trust Corp.',
    'MLM': 'Martin Marietta Materials Inc.',
    'STZ': 'Constellation Brands Inc.',
    'FANG': 'Diamondback Energy Inc.',
    'PPG': 'PPG Industries Inc.',
    'CHTR': 'Charter Communications Inc.',
    'GWW': 'W.W. Grainger Inc.',
    'ES': 'Eversource Energy',
    'EQR': 'Equity Residential',
    'CDW': 'CDW Corp.',
    'BRO': 'Brown & Brown Inc.',
    'PCAR': 'PACCAR Inc.',
    'TROW': 'T. Rowe Price Group Inc.',
    'AVB': 'AvalonBay Communities Inc.',
    'ZBH': 'Zimmer Biomet Holdings Inc.',
    'ATO': 'Atmos Energy Corp.',
    'LH': 'Labcorp Holdings Inc.',
    'PKI': 'PerkinElmer Inc.',
    'EXPD': 'Expeditors International of Washington Inc.',
    'IFF': 'International Flavors & Fragrances Inc.',
    'GPN': 'Global Payments Inc.',
    'CHD': 'Church & Dwight Co. Inc.',
    'MTB': 'M&T Bank Corp.',
    'A': 'Agilent Technologies Inc.',
    'SBAC': 'SBA Communications Corp.',
    'EIX': 'Edison International',
    'HUBB': 'Hubbell Inc.',
    'WST': 'West Pharmaceutical Services Inc.',
    'SWKS': 'Skyworks Solutions Inc.',
    'PEG': 'Public Service Enterprise Group Inc.',
    'DOV': 'Dover Corp.',
    'FRC': 'First Republic Bank',
    'FITB': 'Fifth Third Bancorp',
    'HBAN': 'Huntington Bancshares Inc.',
    'KEY': 'KeyCorp',
    'RF': 'Regions Financial Corp.',
    'AES': 'AES Corp.',
    'K': 'Kellogg Co.',
    'STE': 'STERIS PLC',
    'VICI': 'VICI Properties Inc.',
    'WELL': 'Welltower Inc.',
    'MAA': 'Mid-America Apartment Communities Inc.',
    'UDR': 'UDR Inc.',
    'ESS': 'Essex Property Trust Inc.',
    'CPT': 'Camden Property Trust',
    'ARE': 'Alexandria Real Estate Equities Inc.',
    'VTR': 'Ventas Inc.',
    'DLR': 'Digital Realty Trust Inc.',
    'BXP': 'Boston Properties Inc.',
    'HST': 'Host Hotels & Resorts Inc.',
    'REG': 'Regency Centers Corp.',
    'FRT': 'Federal Realty Investment Trust',
    'KIM': 'Kimco Realty Corp.',
    'UE': 'Urban Edge Properties',
    'WPC': 'W. P. Carey Inc.',
    'NNN': 'National Retail Properties Inc.',
    'ADC': 'Agree Realty Corp.',
    'STAG': 'Stag Industrial Inc.'
}

# Helper functions
async def get_cik_from_ticker(ticker: str) -> Optional[str]:
    """Get CIK number from ticker using SEC's company tickers API"""
    try:
        async with httpx.AsyncClient() as client:
            # Add user agent as required by SEC
            headers = {"User-Agent": "QuickFilings API (contact@quickfilings.com)"}
            response = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=headers
            )
            if response.status_code == 200:
                companies = response.json()
                for company_data in companies.values():
                    if company_data.get('ticker', '').upper() == ticker.upper():
                        cik = str(company_data['cik_str']).zfill(10)
                        return cik
        return None
    except Exception as e:
        print(f"Error getting CIK for {ticker}: {e}")
        return None

async def get_sec_filings(cik: str, file_types: List[str], quarters_back: int, annuals_back: int) -> List[FileItem]:
    """Fetch SEC filings from EDGAR API"""
    files = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"User-Agent": "QuickFilings API (contact@quickfilings.com)"}
            
            # Get company submissions
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                filings = data.get('filings', {}).get('recent', {})
                
                if filings:
                    # Process filings
                    for i, form_type in enumerate(filings.get('form', [])):
                        try:
                            filing_date = filings.get('filingDate', [])[i]
                            accession_number = filings.get('accessionNumber', [])[i]
                            
                            # Skip if too old
                            filing_date_obj = datetime.strptime(filing_date, '%Y-%m-%d')
                            cutoff_date = datetime.now() - timedelta(days=365 * 6)  # 6 years max
                            if filing_date_obj < cutoff_date:
                                continue
                            
                            file_item = None
                            
                            # Handle different filing types
                            if 'quarterlyAnnual' in file_types:
                                if form_type == '10-K' and annuals_back > 0:
                                    # Check if this annual report is within our limit
                                    year = filing_date_obj.year
                                    current_year = datetime.now().year
                                    if (current_year - year) < annuals_back:
                                        file_item = FileItem(
                                            name=f"10K_{year}_{accession_number.replace('-', '')}.pdf",
                                            type="10-K Annual Filing",
                                            date=filing_date,
                                            size="2.5 MB",
                                            url=f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession_number.replace('-', '')}/{accession_number}.txt"
                                        )
                                
                                elif form_type == '10-Q' and quarters_back > 0:
                                    # Check if this quarterly report is within our limit
                                    months_back = quarters_back * 3
                                    cutoff = datetime.now() - timedelta(days=months_back * 30)
                                    if filing_date_obj >= cutoff:
                                        quarter = f"Q{((filing_date_obj.month - 1) // 3) + 1}"
                                        file_item = FileItem(
                                            name=f"10Q_{quarter}_{filing_date_obj.year}_{accession_number.replace('-', '')}.pdf",
                                            type="10-Q Quarterly Filing",
                                            date=filing_date,
                                            size="1.8 MB",
                                            url=f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession_number.replace('-', '')}/{accession_number}.txt"
                                        )
                                
                                elif form_type == 'DEF 14A' and annuals_back > 0:
                                    year = filing_date_obj.year
                                    current_year = datetime.now().year
                                    if (current_year - year) < annuals_back:
                                        file_item = FileItem(
                                            name=f"DEF14A_{year}_{accession_number.replace('-', '')}.pdf",
                                            type="Proxy Statement",
                                            date=filing_date,
                                            size="3.1 MB",
                                            url=f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession_number.replace('-', '')}/{accession_number}.txt"
                                        )
                            
                            if 'form8k' in file_types and form_type == '8-K':
                                # Get recent 8-K filings
                                if filing_date_obj >= datetime.now() - timedelta(days=365):
                                    file_item = FileItem(
                                        name=f"8K_{filing_date}_{accession_number.replace('-', '')}.pdf",
                                        type="8-K Current Report",
                                        date=filing_date,
                                        size="650 KB",
                                        url=f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession_number.replace('-', '')}/{accession_number}.txt"
                                    )
                            
                            if file_item:
                                files.append(file_item)
                                
                        except (IndexError, ValueError) as e:
                            continue
                    
    except Exception as e:
        print(f"Error fetching SEC filings: {e}")
    
    return files

async def scrape_company_ir_site(ticker: str, file_types: List[str], quarters_back: int) -> List[FileItem]:
    """Scrape company investor relations sites for earnings and presentations"""
    files = []
    
    # Common IR site patterns
    ir_urls = [
        f"https://investor.{ticker.lower()}.com",
        f"https://{ticker.lower()}.com/investors",
        f"https://{ticker.lower()}.com/investor-relations",
        f"https://investors.{ticker.lower()}.com",
        f"https://ir.{ticker.lower()}.com"
    ]
    
    # Special cases for major companies
    special_urls = {
        'AAPL': 'https://investor.apple.com',
        'MSFT': 'https://www.microsoft.com/en-us/Investor',
        'GOOGL': 'https://abc.xyz/investor',
        'AMZN': 'https://ir.aboutamazon.com',
        'TSLA': 'https://ir.tesla.com',
        'META': 'https://investor.fb.com',
        'NVDA': 'https://investor.nvidia.com',
        'JPM': 'https://www.jpmorganchase.com/ir',
        'V': 'https://investor.visa.com',
        'WMT': 'https://corporate.walmart.com/our-story/our-business/financial-information'
    }
    
    if ticker.upper() in special_urls:
        ir_urls.insert(0, special_urls[ticker.upper()])
    
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            for url in ir_urls:
                try:
                    response = await client.get(url, headers=headers)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Look for earnings and presentation links
                        if 'earnings' in file_types:
                            earnings_files = await find_earnings_files(soup, url, quarters_back)
                            files.extend(earnings_files)
                        
                        if 'presentations' in file_types:
                            presentation_files = await find_presentation_files(soup, url, quarters_back)
                            files.extend(presentation_files)
                        
                        # If we found files, break from trying other URLs
                        if files:
                            break
                            
                except Exception as e:
                    continue
                    
        # Rate limiting
        await asyncio.sleep(1)
        
    except Exception as e:
        print(f"Error scraping IR site for {ticker}: {e}")
    
    return files

async def find_earnings_files(soup: BeautifulSoup, base_url: str, quarters_back: int) -> List[FileItem]:
    """Find earnings presentation files from IR page"""
    files = []
    
    # Common patterns for earnings links
    earnings_patterns = [
        r'earnings.*call',
        r'quarterly.*results',
        r'Q[1-4].*\d{4}.*earnings',
        r'earnings.*presentation',
        r'financial.*results'
    ]
    
    # Look for links that might be earnings files
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True).lower()
        
        # Check if this looks like an earnings file
        is_earnings = any(re.search(pattern, text, re.IGNORECASE) for pattern in earnings_patterns)
        is_pdf = href.lower().endswith('.pdf') or 'pdf' in href.lower()
        
        if is_earnings and is_pdf:
            # Try to extract date/quarter info
            quarter_match = re.search(r'Q([1-4])\s*(\d{4})', text, re.IGNORECASE)
            year_match = re.search(r'(\d{4})', text)
            
            if quarter_match:
                quarter, year = quarter_match.groups()
                file_date = f"{year}-{int(quarter) * 3:02d}-15"  # Approximate date
            elif year_match:
                year = year_match.group(1)
                file_date = f"{year}-12-31"  # Default to end of year
            else:
                file_date = "2025-01-01"  # Default current
            
            # Create absolute URL
            file_url = urljoin(base_url, href)
            
            files.append(FileItem(
                name=f"Earnings_Call_{file_date.replace('-', '_')}.pdf",
                type="Earnings Presentation",
                date=file_date,
                size="850 KB",
                url=file_url
            ))
    
    return files[:quarters_back]  # Limit to requested number

async def find_presentation_files(soup: BeautifulSoup, base_url: str, quarters_back: int) -> List[FileItem]:
    """Find investor presentation files from IR page"""
    files = []
    
    # Common patterns for presentation links
    presentation_patterns = [
        r'investor.*presentation',
        r'corporate.*presentation',
        r'conference.*presentation',
        r'analyst.*day',
        r'investor.*day'
    ]
    
    # Look for links that might be presentation files
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True).lower()
        
        # Check if this looks like a presentation file
        is_presentation = any(re.search(pattern, text, re.IGNORECASE) for pattern in presentation_patterns)
        is_pdf = href.lower().endswith('.pdf') or 'pdf' in href.lower()
        
        if is_presentation and is_pdf:
            # Try to extract date info
            year_match = re.search(r'(\d{4})', text)
            
            if year_match:
                year = year_match.group(1)
                file_date = f"{year}-06-15"  # Default to mid-year
            else:
                file_date = "2025-01-01"  # Default current
            
            # Create absolute URL
            file_url = urljoin(base_url, href)
            
            files.append(FileItem(
                name=f"Investor_Presentation_{file_date.replace('-', '_')}.pdf",
                type="Investor Presentation",
                date=file_date,
                size="4.2 MB",
                url=file_url
            ))
    
    return files[:quarters_back]  # Limit to requested number

# Download proxy endpoints
@app.get("/download")
async def download_file(url: str, filename: str = None):
    """Proxy download endpoint to handle CORS and direct downloads"""
    
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": "QuickFilings API (contact@quickfilings.com)",
                "Accept": "application/pdf,application/octet-stream,*/*"
            }
            
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                # Determine content type
                content_type = response.headers.get('content-type', 'application/octet-stream')
                
                # Set filename if not provided
                if not filename:
                    # Try to extract from URL
                    filename = url.split('/')[-1]
                    if '.' not in filename:
                        filename = f"document.pdf"
                
                # Create streaming response
                def generate():
                    for chunk in response.iter_bytes(chunk_size=8192):
                        yield chunk
                
                headers = {
                    "Content-Disposition": f"attachment; filename={filename}",
                    "Content-Type": content_type,
                    "Content-Length": str(len(response.content)) if response.content else None
                }
                
                # Remove None values
                headers = {k: v for k, v in headers.items() if v is not None}
                
                return StreamingResponse(
                    io.BytesIO(response.content),
                    media_type=content_type,
                    headers=headers
                )
            else:
                raise HTTPException(status_code=response.status_code, detail="File not accessible")
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

@app.get("/proxy")
async def proxy_file(url: str):
    """Simple proxy endpoint for viewing files without download"""
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": "QuickFilings API (contact@quickfilings.com)"
            }
            
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', 'application/octet-stream')
                
                return StreamingResponse(
                    io.BytesIO(response.content),
                    media_type=content_type
                )
            else:
                raise HTTPException(status_code=response.status_code, detail="File not accessible")
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proxy failed: {str(e)}")

@app.get("/")
async def root():
    return {"message": "QuickFilings API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/search", response_model=SearchResponse)
async def search_company(
    request: Request,
    ticker: str,
    file_types: List[str],
    quarters_back: int = 4,
    annuals_back: int = 5,
    exchange: str = "auto"
):
    """Search for company filings and presentations"""
    
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker symbol is required")
    
    ticker = ticker.upper().strip()
    
    # Get CIK for SEC API
    cik = await get_cik_from_ticker(ticker)
    if not cik:
        raise HTTPException(status_code=404, detail=f"Company not found for ticker: {ticker}")
    
    # Create company data
    company_data = CompanyData(
        ticker=ticker,
        name=company_name,
        cik=cik,
        exchange=exchange if exchange != "auto" else "NASDAQ"
    )
    
    # Fetch files from different sources
    all_files = []
    
    # Get SEC filings
    sec_files = await get_sec_filings(cik, file_types, quarters_back, annuals_back)
    all_files.extend(sec_files)
    
    # Get IR site files for earnings and presentations
    if 'earnings' in file_types or 'presentations' in file_types:
        ir_files = await scrape_company_ir_site(ticker, file_types, quarters_back)
        all_files.extend(ir_files)
    
    # Remove duplicates and sort by date
    unique_files = []
    seen_names = set()
    
    for file in all_files:
        if file.name not in seen_names:
            # Add download URLs using our proxy endpoints
            original_url = file.url
            file.url = f"{request.url.scheme}://{request.url.netloc}/proxy?url={original_url}"
            file.download_url = f"{request.url.scheme}://{request.url.netloc}/download?url={original_url}&filename={file.name}"
            
            unique_files.append(file)
            seen_names.add(file.name)
    
    # Sort by date (newest first)
    unique_files.sort(key=lambda x: x.date, reverse=True)
    
    return SearchResponse(
        company=company_data,
        files=unique_files
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)