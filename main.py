from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import httpx
import asyncio
from datetime import datetime, timedelta
import logging
import os
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="QuickFilings API",
    description="SEC filings and presentations download service",
    version="1.0.0"
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Models
class SearchRequest(BaseModel):
    ticker: str
    file_types: List[str]
    quarters_back: int = 6
    annuals_back: int = 5
    exchange: str = "auto"

class CompanyInfo(BaseModel):
    name: str
    ticker: str
    cik: str
    exchange: str
    sector: Optional[str] = None
    industry: Optional[str] = None

class FileInfo(BaseModel):
    name: str
    type: str
    date: str
    size: str
    url: str
    form_type: Optional[str] = None
    period_end: Optional[str] = None

class SearchResponse(BaseModel):
    company: CompanyInfo
    files: List[FileInfo]
    total_files: int

# SEC API Configuration
SEC_BASE_URL = "https://data.sec.gov"
SEC_COMPANY_TICKERS_URL = f"{SEC_BASE_URL}/files/company_tickers.json"
SEC_HEADERS = {
    "User-Agent": "QuickFilings/1.0 (contact@quickfilings.com)",
    "Accept": "application/json",
    "Host": "data.sec.gov"
}

# Cache for company data
company_cache = {}
cache_expiry = {}

class SECDataService:
    def __init__(self):
        self.client = httpx.AsyncClient(
            headers=SEC_HEADERS,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=10)
        )
    
    async def get_company_info(self, ticker: str) -> CompanyInfo:
        """Get company information from SEC data"""
        ticker = ticker.upper()
        
        # Check cache first
        if ticker in company_cache and datetime.now() < cache_expiry.get(ticker, datetime.now()):
            return company_cache[ticker]
        
        try:
            # Get company tickers mapping
            response = await self.client.get(SEC_COMPANY_TICKERS_URL)
            response.raise_for_status()
            companies_data = response.json()
            
            # Find company by ticker
            company_info = None
            for company in companies_data.values():
                if company.get('ticker', '').upper() == ticker:
                    company_info = company
                    break
            
            if not company_info:
                raise HTTPException(status_code=404, detail=f"Company with ticker {ticker} not found")
            
            # Get additional company details
            cik = str(company_info['cik_str']).zfill(10)
            company_details = await self._get_company_details(cik)
            
            result = CompanyInfo(
                name=company_info['title'],
                ticker=ticker,
                cik=cik,
                exchange=self._determine_exchange(ticker),
                sector=company_details.get('sector'),
                industry=company_details.get('industry')
            )
            
            # Cache the result
            company_cache[ticker] = result
            cache_expiry[ticker] = datetime.now() + timedelta(hours=24)
            
            return result
            
        except httpx.HTTPError as e:
            logger.error(f"Error fetching company info for {ticker}: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch company information")
    
    async def _get_company_details(self, cik: str) -> Dict[str, Any]:
        """Get additional company details from SEC submissions"""
        try:
            url = f"{SEC_BASE_URL}/submissions/CIK{cik}.json"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            
            return {
                'sector': data.get('sic', ''),
                'industry': data.get('sicDescription', ''),
                'business_description': data.get('businessDescription', ''),
                'filings': data.get('filings', {})
            }
        except Exception as e:
            logger.warning(f"Could not fetch detailed info for CIK {cik}: {e}")
            return {}
    
    def _determine_exchange(self, ticker: str) -> str:
        """Determine exchange based on ticker patterns"""
        if len(ticker) <= 4 and ticker.isalpha():
            return "NASDAQ"
        else:
            return "NYSE"
    
    async def get_company_filings(self, cik: str, file_types: List[str], 
                                quarters_back: int, annuals_back: int) -> List[FileInfo]:
        """Get company filings based on specified criteria"""
        try:
            # Get company submissions
            url = f"{SEC_BASE_URL}/submissions/CIK{cik}.json"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            
            filings_data = data.get('filings', {}).get('recent', {})
            if not filings_data:
                return []
            
            files = []
            
            # Process each filing
            for i in range(len(filings_data.get('form', []))):
                form_type = filings_data['form'][i]
                filing_date = filings_data['filingDate'][i]
                accession_number = filings_data['accessionNumber'][i]
                primary_document = filings_data['primaryDocument'][i]
                
                # Filter based on file types requested
                if self._should_include_filing(form_type, file_types, filing_date, quarters_back, annuals_back):
                    file_info = await self._create_file_info(
                        form_type, filing_date, accession_number, primary_document, cik
                    )
                    if file_info:
                        files.append(file_info)
            
            # Sort by date (newest first)
            files.sort(key=lambda x: x.date, reverse=True)
            
            return files
            
        except Exception as e:
            logger.error(f"Error fetching filings for CIK {cik}: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch company filings")
    
    def _should_include_filing(self, form_type: str, file_types: List[str], 
                             filing_date: str, quarters_back: int, annuals_back: int) -> bool:
        """Determine if a filing should be included based on criteria"""
        filing_datetime = datetime.strptime(filing_date, '%Y-%m-%d')
        current_date = datetime.now()
        
        # Check date range
        quarters_cutoff = current_date - timedelta(days=quarters_back * 90)
        annuals_cutoff = current_date - timedelta(days=annuals_back * 365)
        
        # Map form types to file types
        form_type_mapping = {
            'quarterlyAnnual': ['10-Q', '10-K', '10-K/A', '10-Q/A'],
            'form8k': ['8-K', '8-K/A'],
            'earnings': ['8-K'],
            'presentations': ['8-K', 'DEF 14A']
        }
        
        # Check if form type matches requested file types
        for file_type in file_types:
            if form_type in form_type_mapping.get(file_type, []):
                # Apply date filters
                if form_type in ['10-K', '10-K/A'] and filing_datetime >= annuals_cutoff:
                    return True
                elif form_type in ['10-Q', '10-Q/A', '8-K', '8-K/A'] and filing_datetime >= quarters_cutoff:
                    return True
                elif form_type in ['DEF 14A'] and filing_datetime >= annuals_cutoff:
                    return True
        
        return False
    
    async def _create_file_info(self, form_type: str, filing_date: str, 
                              accession_number: str, primary_document: str, cik: str) -> Optional[FileInfo]:
        """Create FileInfo object for a filing"""
        try:
            # Clean accession number for URL
            accession_clean = accession_number.replace('-', '')
            
            # Construct SEC document URL
            base_url = f"{SEC_BASE_URL}/Archives/edgar/data/{int(cik)}/{accession_clean}"
            doc_url = f"{base_url}/{primary_document}"
            
            # Determine file type description
            type_descriptions = {
                '10-K': 'Annual Report',
                '10-Q': 'Quarterly Report',
                '8-K': 'Current Report',
                'DEF 14A': 'Proxy Statement'
            }
            
            file_type = type_descriptions.get(form_type, form_type)
            
            # Generate display name
            display_name = f"{form_type}_{filing_date.replace('-', '')}"
            if primary_document.endswith('.htm'):
                display_name += '.htm'
            else:
                display_name += '.pdf'
            
            return FileInfo(
                name=display_name,
                type=file_type,
                date=filing_date,
                size="Unknown",
                url=doc_url,
                form_type=form_type,
                period_end=filing_date
            )
            
        except Exception as e:
            logger.warning(f"Could not create file info for {form_type} {accession_number}: {e}")
            return None

# Initialize service
sec_service = SECDataService()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "QuickFilings API",
        "version": "1.0.0"
    }

@app.post("/search", response_model=SearchResponse)
async def search_company_filings(request: SearchRequest):
    """Search for company filings based on ticker and criteria"""
    try:
        logger.info(f"Searching for {request.ticker} with types: {request.file_types}")
        
        # Validate input
        if not request.ticker or len(request.ticker) > 10:
            raise HTTPException(status_code=400, detail="Invalid ticker symbol")
        
        if not request.file_types:
            raise HTTPException(status_code=400, detail="At least one file type must be selected")
        
        # Get company information
        company_info = await sec_service.get_company_info(request.ticker)
        
        # Get company filings
        files = await sec_service.get_company_filings(
            company_info.cik,
            request.file_types,
            request.quarters_back,
            request.annuals_back
        )
        
        logger.info(f"Found {len(files)} files for {request.ticker}")
        
        return SearchResponse(
            company=company_info,
            files=files,
            total_files=len(files)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in search: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/companies/{ticker}")
async def get_company_info_endpoint(ticker: str):
    """Get company information by ticker"""
    try:
        company_info = await sec_service.get_company_info(ticker)
        return company_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting company info for {ticker}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch company information")

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "QuickFilings API",
        "version": "1.0.0",
        "description": "SEC filings and presentations download service",
        "endpoints": {
            "/health": "Health check",
            "/search": "Search company filings (POST)",
            "/companies/{ticker}": "Get company info by ticker",
            "/docs": "API documentation"
        }
    }

if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment variable for deployment platforms
    port = int(os.environ.get("PORT", 8000))
    
    print(f"Starting server on host 0.0.0.0 and port {port}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )
