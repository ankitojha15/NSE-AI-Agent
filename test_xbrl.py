from app.services.nse_service import NseService
from app.services.xbrl_service import XBRLService

nse = NseService()
xbrl = XBRLService()

results = nse.get_company_results("TCS")

xml = xbrl.download_xbrl(results[0]["xbrl"])

print(type(xml))
print(xml[:500])
