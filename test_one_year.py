from app.services.nse_service import NseService
from app.services.one_year_pipeline_service import OneYearPipelineService


nse_service = NseService()

pipeline = OneYearPipelineService(nse_service)

companies = pipeline.get_eligible_companies()

print("\nELIGIBLE COMPANIES:", len(companies))

for symbol, quarters in list(companies.items())[:20]:
    print(symbol, "->", quarters)