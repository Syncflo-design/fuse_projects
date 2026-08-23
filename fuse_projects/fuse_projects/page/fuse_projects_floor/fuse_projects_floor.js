// Fuse — project work on a phone.
//
// A second front door onto the same records the desk uses. Every action goes through
// fuse_projects/floor.py, which saves an ordinary Task or submits an ordinary Timesheet —
// so whatever the desk sends to Intacct, this sends too, by the same path.
//
// Mounted inside page.body (a jQuery object in v16, per CoWork_Helper gotcha
// 2026-05-10-frappe-v16-page-api-drift). HTML is assembled as string arrays joined with
// "\n" — the page-bundle rule from nest_crm_mobile.

frappe.pages['fuse-projects-floor'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Site Work',
		single_column: true
	});

	var BUILD_MARKER = 'v0.1.0-2026-08-21';
	console.log('Fuse Site Work loaded:', BUILD_MARKER);

	wrapper.fuseSiteWork = window.fuseSiteWork = new FuseSiteWork(page);
};

frappe.pages['fuse-projects-floor'].on_page_show = function (wrapper) {
	if (!wrapper.fuseSiteWork) return;
	wrapper.fuseSiteWork.reload();
};

// ---------------------------------------------------------------------------

// What the user picked last, so the second task of the morning is two taps instead of
// four. A site worker is on one project all day.
function fsw_remembered() {
	try {
		return localStorage.getItem('fuse_site_work:project') || '';
	} catch (e) {
		return '';
	}
}

function fsw_remember(value) {
	try {
		localStorage.setItem('fuse_site_work:project', value || '');
	} catch (e) {
		/* private browsing — remembering is a convenience, not a requirement */
	}
}

function fsw_escape(value) {
	return frappe.utils.escape_html(value == null ? '' : String(value));
}

// ---------------------------------------------------------------------------

function FuseSiteWork(page) {
	this.page = page;
	this.context = null;
	this.project = fsw_remembered();
	this.tasks = [];
	this.build();
	this.reload();
}

FuseSiteWork.prototype.build = function () {
	var html = [
		'<div class="fsw">',
		'  <div class="fsw-bar">',
		'    <select class="fsw-project"><option value="">All projects</option></select>',
		'    <input class="fsw-search" type="search" placeholder="Find a task">',
		'  </div>',
		'  <button class="fsw-add">+ Task found on site</button>',
		'  <div class="fsw-list"></div>',
		'</div>'
	].join('\n');

	$(this.page.body).html(html);
	$(this.page.body).append(this.styles());

	var me = this;
	$(this.page.body).find('.fsw-project').on('change', function () {
		me.project = $(this).val();
		fsw_remember(me.project);
		me.load_tasks();
	});

	// Debounced, because a phone keyboard fires this on every letter and each one is a
	// round trip.
	var timer = null;
	$(this.page.body).find('.fsw-search').on('input', function () {
		var value = $(this).val();
		clearTimeout(timer);
		timer = setTimeout(function () {
			me.load_tasks(value);
		}, 300);
	});

	$(this.page.body).find('.fsw-add').on('click', function () {
		me.add_task();
	});
};

FuseSiteWork.prototype.add_task = function () {
	var me = this;
	var projects = (this.context && this.context.projects) || [];

	var dialog = new frappe.ui.Dialog({
		title: 'Task found on site',
		fields: [
			{
				fieldname: 'project',
				fieldtype: 'Select',
				label: 'Project',
				reqd: 1,
				// The picker's own list, not a Link field: this screen already knows which
				// projects are open, and a Link would let someone book work to a closed one.
				options: projects.map(function (p) {
					return { value: p.name, label: p.project_name || p.name };
				}),
				default: this.project || (projects[0] && projects[0].name)
			},
			{ fieldname: 'subject', fieldtype: 'Data', label: 'What needs doing', reqd: 1 },
			{ fieldname: 'description', fieldtype: 'Small Text', label: 'Detail' }
		],
		primary_action_label: 'Add it',
		primary_action: function (values) {
			frappe.call({
				method: 'fuse_projects.floor.create_task',
				args: {
					project: values.project,
					subject: values.subject,
					description: values.description || null
				},
				freeze: true,
				freeze_message: 'Adding…',
				callback: function (r) {
					if (!r || !r.message) return;
					dialog.hide();
					me.project = values.project;
					fsw_remember(me.project);
					$(me.page.body).find('.fsw-project').val(me.project);
					frappe.show_alert({
						message: 'Added ' + fsw_escape(r.message.subject),
						indicator: 'green'
					});
					me.load_tasks();
				}
			});
		}
	});
	dialog.show();
};

FuseSiteWork.prototype.styles = function () {
	// Inline rather than a stylesheet asset: this screen is one list and two buttons, and
	// a build step for forty lines of CSS is not worth the deploy it would need.
	return [
		'<style>',
		'.fsw { padding: 8px 0 32px; }',
		'.fsw-bar { display: flex; gap: 8px; margin-bottom: 12px; }',
		'.fsw-bar select, .fsw-bar input { flex: 1; min-height: 44px; padding: 8px 10px;',
		'  font-size: 16px; border: 1px solid var(--border-color); border-radius: 8px;',
		'  background: var(--control-bg); color: var(--text-color); }',
		'.fsw-task { border: 1px solid var(--border-color); border-radius: 10px;',
		'  padding: 12px; margin-bottom: 10px; background: var(--card-bg); }',
		'.fsw-task h4 { margin: 0 0 4px; font-size: 15px; }',
		'.fsw-meta { font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }',
		'.fsw-actions { display: flex; flex-wrap: wrap; gap: 8px; }',
		'.fsw-actions button { min-height: 44px; flex: 1 1 30%; border-radius: 8px;',
		'  border: 1px solid var(--border-color); background: var(--control-bg);',
		'  color: var(--text-color); font-size: 14px; }',
		'.fsw-actions button.fsw-on { background: var(--primary); color: white;',
		'  border-color: var(--primary); }',
		'.fsw-actions button.fsw-time { flex-basis: 100%; }',
		'.fsw-add { width: 100%; min-height: 44px; margin-bottom: 12px; border-radius: 8px;',
		'  border: 1px dashed var(--border-color); background: transparent;',
		'  color: var(--text-muted); font-size: 14px; }',
		'.fsw-empty { padding: 32px 8px; text-align: center; color: var(--text-muted); }',
		'</style>'
	].join('\n');
};

FuseSiteWork.prototype.reload = function () {
	var me = this;
	frappe.call({
		method: 'fuse_projects.floor.context',
		callback: function (r) {
			if (!r || !r.message) return;
			me.context = r.message;
			me.draw_projects();
			me.load_tasks();
		}
	});
};

FuseSiteWork.prototype.draw_projects = function () {
	var options = ['<option value="">All projects</option>'];
	(this.context.projects || []).forEach(function (project) {
		options.push(
			'<option value="' + fsw_escape(project.name) + '">' +
			fsw_escape(project.project_name || project.name) +
			'</option>'
		);
	});
	var select = $(this.page.body).find('.fsw-project');
	select.html(options.join('\n'));
	if (this.project) select.val(this.project);
	// The remembered project may have been closed since. Fall back to all rather than
	// showing an empty list that looks like there is no work.
	if (select.val() !== this.project) {
		this.project = '';
		fsw_remember('');
	}
};

FuseSiteWork.prototype.load_tasks = function (search) {
	var me = this;
	frappe.call({
		method: 'fuse_projects.floor.tasks',
		args: { project: this.project || null, search: search || null },
		callback: function (r) {
			me.tasks = (r && r.message) || [];
			me.draw_tasks();
		}
	});
};

FuseSiteWork.prototype.draw_tasks = function () {
	var me = this;
	var body = $(this.page.body).find('.fsw-list');

	if (!this.tasks.length) {
		body.html('<div class="fsw-empty">No open tasks.</div>');
		return;
	}

	var statuses = (this.context && this.context.statuses) || [];
	var can_log_time = !!(this.context && this.context.employee);
	var shows_intacct = !!(this.context && this.context.intacct);

	var html = this.tasks.map(function (task) {
		var buttons = statuses.map(function (status) {
			return (
				'<button data-task="' + fsw_escape(task.name) + '" data-status="' + fsw_escape(status) + '"' +
				(task.status === status ? ' class="fsw-on"' : '') +
				'>' + fsw_escape(status) + '</button>'
			);
		});

		if (can_log_time) {
			buttons.push(
				'<button class="fsw-time" data-task="' + fsw_escape(task.name) + '">Log time</button>'
			);
		}

		// The Intacct id earns its place only on a site that has a connection — there it is
		// the first thing an accountant asks about. Without one, saying "not in Intacct" on
		// every row is a true statement nobody asked for.
		var meta = [
			fsw_escape(task.project),
			task.progress ? fsw_escape(task.progress) + '% done' : null,
			shows_intacct && task.custom_intacct_task_id
				? 'Intacct ' + fsw_escape(task.custom_intacct_task_id)
				: null
		].filter(Boolean).join(' · ');

		return [
			'<div class="fsw-task">',
			'  <h4>' + fsw_escape(task.subject || task.name) + '</h4>',
			'  <div class="fsw-meta">' + meta + '</div>',
			'  <div class="fsw-actions">' + buttons.join('') + '</div>',
			'</div>'
		].join('\n');
	}).join('\n');

	body.html(html);

	body.find('button[data-status]').on('click', function () {
		me.set_status($(this).data('task'), $(this).data('status'));
	});
	body.find('button.fsw-time').on('click', function () {
		me.log_time($(this).data('task'));
	});
};

FuseSiteWork.prototype.set_status = function (task, status) {
	var me = this;
	frappe.call({
		method: 'fuse_projects.floor.set_status',
		args: { task: task, status: status },
		freeze: true,
		freeze_message: 'Updating…',
		callback: function (r) {
			if (!r || !r.message) return;
			frappe.show_alert({ message: task + ' → ' + r.message.status, indicator: 'green' });
			me.load_tasks($(me.page.body).find('.fsw-search').val());
		}
	});
};

FuseSiteWork.prototype.log_time = function (task) {
	var me = this;
	var dialog = new frappe.ui.Dialog({
		title: 'Log time',
		fields: [
			{ fieldname: 'hours', fieldtype: 'Float', label: 'Hours', reqd: 1 },
			{ fieldname: 'activity_type', fieldtype: 'Link', label: 'Activity', options: 'Activity Type' },
			{ fieldname: 'notes', fieldtype: 'Small Text', label: 'What was done' }
		],
		primary_action_label: 'Book it',
		primary_action: function (values) {
			frappe.call({
				method: 'fuse_projects.floor.log_time',
				args: {
					task: task,
					hours: values.hours,
					activity_type: values.activity_type || null,
					notes: values.notes || null
				},
				freeze: true,
				freeze_message: 'Booking…',
				callback: function (r) {
					if (!r || !r.message) return;
					dialog.hide();
					frappe.show_alert({
						message: r.message.hours + 'h booked on ' + task,
						indicator: 'green'
					});
					me.load_tasks($(me.page.body).find('.fsw-search').val());
				}
			});
		}
	});
	dialog.show();
};
