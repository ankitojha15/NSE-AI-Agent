from app.services.nse_service import NseService

service = NseService()

results = service.get_company_results("TCS")

print(len(results))

for result in results:
    print(result)