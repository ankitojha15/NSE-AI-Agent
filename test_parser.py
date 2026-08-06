from app.services.nse_service import NseService
from app.services.xbrl_service import XBRLService
from app.services.xbrl_parser import XBRLParser

nse = NseService()
xbrl = XBRLService()
parser = XBRLParser()

results = nse.get_company_results("TCS")

xml = xbrl.download_xbrl(results[0]["xbrl"])

root = parser.parse(xml)

financials = parser.extract_financial_data(root)

print(financials)