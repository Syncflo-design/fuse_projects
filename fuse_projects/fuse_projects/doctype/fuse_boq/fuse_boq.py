import frappe
from frappe.model.document import Document
from frappe.utils import flt, fmt_money

# A line priced from its build-up takes the sum of these as its rate.
BUILD_UP = ("labour_rate", "plant_rate", "material_rate", "subcontract_rate")


class FuseBOQ(Document):
	def validate(self):
		if self.contract_model == "EPC" and not self.customer:
			frappe.throw("An EPC job is billed to a client. Choose the client.")
		self.project_key = (self.project_key or "").strip()
		for row in self.items:
			row.section = (row.section or "").strip()

		self._price()

		# Once awarded, the BOQ is the budget the cost report measures against. Changing the
		# price or the code afterwards would move the baseline under figures already reported.
		if self.status == "Awarded" and not self.flags.awarding:
			before = self.get_doc_before_save()
			if before and (
				flt(before.total_cost, 2) != flt(self.total_cost, 2)
				or flt(before.contract_value, 2) != flt(self.contract_value, 2)
				or before.project_key != self.project_key
			):
				frappe.throw("This BOQ is awarded. Its price and code are the job's budget and cannot change.")

	def _price(self):
		for row in self.items:
			built = sum(flt(row.get(field)) for field in BUILD_UP)
			if built:
				row.rate = built
			row.amount = flt(flt(row.qty) * flt(row.rate), 2)

		self.total_cost = flt(sum(flt(row.amount) for row in self.items), 2)
		self.contract_value = flt(self.total_cost * (1 + flt(self.markup_percent) / 100), 2)

	def get_sections(self):
		"""BOQ sections in the order they first appear, with budget (cost) and contract value."""
		sections = {}
		for row in self.items:
			if not row.section:
				continue
			section = sections.setdefault(
				row.section,
				{"section": row.section, "idx": len(sections) + 1, "cost": 0.0, "task": row.task},
			)
			section["cost"] += flt(row.amount)
			section["task"] = section["task"] or row.task

		factor = 1 + flt(self.markup_percent) / 100
		for section in sections.values():
			section["cost"] = flt(section["cost"], 2)
			section["contract"] = flt(section["cost"] * factor, 2)
			section["description"] = f"BOQ section. Budget {fmt_money(section['cost'], currency=self._currency())}"
		return list(sections.values())

	def _currency(self):
		company = frappe.db.get_value("Project", self.project, "company") if self.project else None
		company = company or frappe.defaults.get_user_default("Company")
		return frappe.get_cached_value("Company", company, "default_currency") if company else None
