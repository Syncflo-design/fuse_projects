import frappe
from frappe.model.document import Document
from frappe.utils import flt

from fuse_projects import commercial


class FuseClientValuation(Document):
	def validate(self):
		boq = frappe.get_doc("Fuse BOQ", self.boq)
		if boq.status != "Awarded":
			frappe.throw(f"{self.boq} is not awarded.")
		if boq.contract_model != "EPC":
			frappe.throw("An IPP plant is NSE's own. It capitalises at COD; there is no client to value it to.")
		self.project = boq.project
		self.customer = boq.customer

		sections = {section["section"]: section for section in boq.get_sections()}
		if not self.lines:
			for line in commercial.valuation_lines(self.boq, exclude=self.name)["lines"]:
				self.append("lines", line)

		for line in self.lines:
			section = sections.get(line.section)
			if not section:
				frappe.throw(f"{line.section} is not a section of {self.boq}.")
			percent = flt(line.percent_complete)
			if percent < 0 or percent > 100:
				frappe.throw(f"{line.section}: percent complete must be between 0 and 100.")
			line.task = section["task"]
			line.contract_value = section["contract"]
			line.value_to_date = flt(section["contract"] * percent / 100, 2)

		self.gross_to_date = flt(sum(flt(line.value_to_date) for line in self.lines), 2)
		self.previously_valued = commercial.previously_valued(self.boq, exclude=self.name)
		self.gross_this_valuation = flt(self.gross_to_date - self.previously_valued, 2)
		self.retention_amount = flt(self.gross_this_valuation * flt(self.retention_percent) / 100, 2)
		self.net_due = flt(self.gross_this_valuation - self.retention_amount, 2)

	def before_submit(self):
		if self.gross_this_valuation <= 0:
			frappe.throw("Nothing new to value since the last valuation.")

	def on_submit(self):
		# Intacct first. A rejection raises, and the submit rolls back with it.
		commercial.post_valuation(self)

		# Progress lands on the task too — the same figure the site team sees on the phone
		# screen, and the one the cost report earns value against.
		for line in self.lines:
			if line.task:
				frappe.db.set_value("Task", line.task, "progress", flt(line.percent_complete), update_modified=False)

	def before_cancel(self):
		if self.intacct_key:
			frappe.throw(
				f"This valuation is Intacct invoice {self.intacct_key}. A superseded valuation is a "
				"credit and a re-issue in Intacct, not a cancellation here."
			)
