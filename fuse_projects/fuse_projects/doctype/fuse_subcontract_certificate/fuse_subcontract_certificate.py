import frappe
from frappe.model.document import Document
from frappe.utils import flt


class FuseSubcontractCertificate(Document):
	def validate(self):
		boq = frappe.db.get_value("Fuse BOQ", self.boq, ["status", "project"], as_dict=True)
		if not boq or boq.status != "Awarded":
			frappe.throw(f"{self.boq} is not awarded. Certificates are raised against an awarded job.")
		self.project = boq.project

		if frappe.db.get_value("Task", self.task, "project") != self.project:
			frappe.throw(f"{self.task} is not a section of {self.project}.")

		if flt(self.gross_value) <= 0:
			frappe.throw("Work certified must be more than zero.")
		self.retention_amount = flt(flt(self.gross_value) * flt(self.retention_percent) / 100, 2)
		self.net_payable = flt(flt(self.gross_value) - self.retention_amount - flt(self.contra_charges), 2)
		if self.net_payable <= 0:
			frappe.throw("Retention and contra-charges take this certificate to nothing payable.")
