frappe.query_reports["Project Cost Report"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			reqd: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "cost_variance" && data && flt(data.cost_variance) < 0) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		if (data && data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
