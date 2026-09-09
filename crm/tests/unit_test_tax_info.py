"""BatchData tax-pull flattening: listing taxes, deeds, foreclosure."""

import unittest

from crm.tests.frappe_shim import install

install()

from crm.api.tax_info import _dd_from_raw, _parse_property  # noqa: E402


POPLAR = {
	"ids": {"apn": "6157-012-010"},
	"owner": {
		"fullName": "PENNYMAC LOAN SERVICES LLC",
		"ownerOccupied": False,
		"ownerStatusType": "Company Owned",
		"mailingAddress": {
			"street": "3043 Townsgate Rd Ste 200",
			"city": "Westlake Village",
			"state": "CA",
			"zip": "91361",
		},
	},
	"tax": {},
	"assessment": {},
	"valuation": {"estimatedValue": 572374, "equityPercent": 100},
	"quickLists": {"taxDefault": False, "freeAndClear": True, "preforeclosure": False},
	"openLien": {"totalOpenLienCount": 0},
	"foreclosure": {
		"status": "Notice of Sale",
		"documentType": "Notice of Trustee Sale",
		"recordingDate": "2025-08-04T00:00:00.000Z",
		"caseNumber": "129377-CA",
		"borrowerName": "Jambon Nola T",
		"trusteeName": "Clear Recon Corp",
	},
	"deedHistory": [
		{
			"buyers": ["PENNYMAC LOAN SERVICES LLC"],
			"sellers": ["CLEAR RECON CORP"],
			"recordingDate": "2026-04-09T00:00:00.000Z",
			"documentType": "Trustee's Deed (Certificate of Title)",
			"salePrice": 574000,
			"foreclosure": True,
		},
		{
			"buyers": ["JAMBON NOLA T"],
			"sellers": ["ESCOBAR HORTENCIA"],
			"recordingDate": "2001-04-11T00:00:00.000Z",
			"documentType": "Grant Deed",
			"salePrice": 115000,
		},
	],
	"mortgageHistory": [
		{
			"recordingDate": "2012-10-26T00:00:00.000Z",
			"lenderName": "PENNYMAC LOAN SERVICES LLC",
			"loanAmount": 201465,
			"loanType": "FHA",
			"interestRate": 3.43,
		}
	],
	"listing": {
		"taxes": [
			{"year": 2026},
			{"amount": 4099.51, "year": 2025},
			{"amount": 4056.44, "year": 2024},
		]
	},
	"general": {"vacant": False},
}


class TaxInfoParseTests(unittest.TestCase):
	def test_listing_tax_fills_annual_when_assessor_block_empty(self):
		parsed = _parse_property(POPLAR)
		self.assertEqual(parsed["apn"], "6157-012-010")
		self.assertEqual(parsed["owner_name"], "PENNYMAC LOAN SERVICES LLC")
		self.assertEqual(parsed["annual_tax"], 4099.51)
		self.assertEqual(parsed["tax_year"], 2025)
		self.assertEqual(parsed["tax_status"], "Taxes current")
		self.assertEqual(parsed["estimated_value"], 572374)

	def test_dd_tables(self):
		dd = _dd_from_raw(POPLAR)
		self.assertEqual(dd["open_lien_count"], 0)
		self.assertTrue(dd["free_and_clear"])
		self.assertEqual(dd["foreclosure"]["case"], "129377-CA")
		self.assertEqual(dd["deeds"][0]["price"], 574000)
		self.assertTrue(dd["deeds"][0]["foreclosure"])
		self.assertEqual(dd["mortgages"][0]["lender"], "PENNYMAC LOAN SERVICES LLC")
		self.assertEqual(dd["taxes"][0]["year"], 2025)
		self.assertIn("Westlake Village", dd["mailing"])

	def test_empty_raw(self):
		self.assertEqual(_dd_from_raw({}), {})
		self.assertEqual(_parse_property({})["matched"], 0)


if __name__ == "__main__":
	unittest.main()
