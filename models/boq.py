# models/boq.py
# -*- coding: utf-8 -*-
import re
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class ConstructionBOQ(models.Model):
    _name = 'construction.boq'
    _description = 'Construction Bill of Quantities'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # -- Header Fields --
    name = fields.Char(string='BOQ Reference', required=True, copy=False, default='New', tracking=True)
    active = fields.Boolean(string='Active', default=True, help="Set to False to hide old versions.")
    
    project_id = fields.Many2one('project.project', string='Project', required=True, tracking=True, help="Select the construction project this BOQ belongs to.")
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', required=True, tracking=True, help="Select the analytic account for cost tracking and budget analysis.")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    
    # -- Versioning Fields --
    version = fields.Integer(string='Version', default=1, required=True, readonly=True, copy=False, help="Version number of the BOQ, incremented on revision.")
    previous_boq_id = fields.Many2one('construction.boq', string='Previous Version', readonly=True, copy=False)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('locked', 'Locked'),
        ('closed', 'Closed')
    ], string='Status', default='draft', required=True, tracking=True, copy=False, help="Current status of the BOQ workflow.")
    
    approval_date = fields.Date(string='Approval Date', readonly=True, copy=False, tracking=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False, tracking=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency', readonly=True)
    
    boq_line_ids = fields.One2many('construction.boq.line', 'boq_id', string='BOQ Lines')
    total_budget = fields.Monetary(string='Total Budget', compute='_compute_total_budget', currency_field='currency_id', store=True, tracking=True)
    
    revision_ids = fields.One2many('construction.boq.revision', 'original_boq_id', string='Revisions (Technical)', copy=False)
    
    display_revision_ids = fields.Many2many('construction.boq.revision', compute='_compute_display_revision_ids', string='Revision History')

    @api.depends('project_id', 'revision_ids')
    def _compute_display_revision_ids(self):
        """Optimized: Single database query for all records"""
        if not self:
            self.display_revision_ids = False
            return
            
        # Get all project IDs in batch
        project_ids = self.mapped('project_id').ids
        if not project_ids:
            self.display_revision_ids = False
            return
            
        # Single query for all revisions related to these projects
        revisions = self.env['construction.boq.revision'].search([
            '|', ('original_boq_id.project_id', 'in', project_ids),
                 ('new_boq_id.project_id', 'in', project_ids)
        ])
        
        # Create mapping for efficient assignment
        revision_map = {}
        for revision in revisions:
            # Map by original BOQ's project
            original_project_id = revision.original_boq_id.project_id.id
            revision_map.setdefault(original_project_id, []).append(revision.id)
            # Map by new BOQ's project
            new_project_id = revision.new_boq_id.project_id.id
            revision_map.setdefault(new_project_id, []).append(revision.id)
        
        # Assign revisions in batch
        for boq in self:
            revision_ids = revision_map.get(boq.project_id.id, [])
            boq.display_revision_ids = [(6, 0, revision_ids)]

    @api.depends('boq_line_ids.budget_amount', 'currency_id')
    def _compute_total_budget(self):
        """Optimized: Use sum with mapping for better performance"""
        for rec in self:
            rec.total_budget = sum(rec.boq_line_ids.mapped('budget_amount'))

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.project_id.account_id:
            self.analytic_account_id = self.project_id.account_id

    # -- Workflow Actions --
    def action_submit(self):
        """Optimized: Batch validation and write"""
        # Validate all records first
        boqs_without_lines = self.filtered(lambda r: not r.boq_line_ids)
        if boqs_without_lines:
            raise ValidationError(_('You cannot submit a BOQ with no lines.'))
        
        # Batch write
        self.write({'state': 'submitted'})

    def action_approve(self):
        """Optimized: Batch operations"""
        self._check_boq_before_approval()
        self._check_one_active_boq()
        
        # Batch write
        self.write({
            'state': 'approved', 
            'approval_date': fields.Date.today(), 
            'approved_by': self.env.user.id
        })

    def action_lock(self):
        """Optimized: Batch write"""
        self.write({'state': 'locked'})

    def action_close(self):
        """Optimized: Batch write"""
        self.write({'state': 'closed'})

    def action_view_history(self):
        self.ensure_one()
        return {
            'name': _('Version History'),
            'type': 'ir.actions.act_window',
            'res_model': 'construction.boq',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.project_id.id), ('id', '!=', self.id)],
            'context': {'active_test': False}, 
        }

    def action_revise(self):
        self.create_revision_snapshot()
        return True

    # -------------------------------------------------------------------------
    # COPY-ON-WRITE (AUTO VERSIONING) LOGIC - OPTIMIZED
    # -------------------------------------------------------------------------

    def create_revision_snapshot(self):
        """Optimized: Batch operations for revision creation"""
        # Filter only records that need revision
        boqs_to_revise = self.filtered(
            lambda b: b.state in ['submitted', 'approved', 'locked']
        )
        
        if not boqs_to_revise:
            return
            
        # Prepare batch operations
        revision_vals_list = []
        boq_update_vals = {}
        messages_to_post = []
        
        for boq in boqs_to_revise:
            # 1. Clean Name Logic
            base_name = re.sub(r' \(v\d+\)$', '', boq.name)
            history_name = f"{base_name} (v{boq.version})"
            
            # 2. Create the snapshot (Copy)
            history_boq = boq.with_context(revision_copy=True, mail_create_nosubscribe=True).copy({
                'name': history_name,
                'active': False,
                'state': 'locked',
                'version': boq.version,
                'previous_boq_id': boq.previous_boq_id.id,
            })

            # 3. Prepare Audit Trail Entry
            revision_vals_list.append({
                'original_boq_id': history_boq.id,
                'new_boq_id': boq.id,
                'revision_reason': "Auto-revision due to modification.",
                'approved_by': boq.approved_by.id,
                'approval_date': boq.approval_date,
            })

            # 4. Prepare values for current record update
            new_version = boq.version + 1
            new_name = f"{base_name} (v{new_version})"
            
            boq_update_vals[boq.id] = {
                'version': new_version,
                'name': new_name,
                'previous_boq_id': history_boq.id,
                'state': 'draft',
                'approval_date': False,
                'approved_by': False,
            }
            
            # Prepare messages for batch posting
            messages_to_post.append((boq, f"Content modified. Archived v{new_version-1} and upgraded to v{new_version}."))
        
        # 5. Batch create revision records
        if revision_vals_list:
            self.env['construction.boq.revision'].create(revision_vals_list)
        
        # 6. Batch update BOQs using write with dictionary mapping
        for boq_id, vals in boq_update_vals.items():
            super(ConstructionBOQ, self.browse(boq_id)).write(vals)
        
        # 7. Batch post messages (if needed, though Odoo doesn't support batch message_post)
        for boq, body in messages_to_post:
            boq.message_post(body=body)

    def write(self, vals):
        if self.env.context.get('revision_copy'):
            return super(ConstructionBOQ, self).write(vals)

        ignore_fields = [
            'message_follower_ids', 'state', 'approval_date', 'approved_by', 
            'active', 'total_budget', 'previous_boq_id', 'revision_ids', 
            'display_revision_ids', 'write_date', 'write_uid', 'name'
        ]
        
        has_business_changes = any(f not in ignore_fields for f in vals)

        if has_business_changes:
            # Filter only BOQs that need revision
            boqs_to_revise = self.filtered(
                lambda b: b.state in ['submitted', 'approved', 'locked']
            )
            if boqs_to_revise:
                boqs_to_revise.create_revision_snapshot()

        return super(ConstructionBOQ, self).write(vals)

    # -------------------------------------------------------------------------
    # CONSTRAINTS - OPTIMIZED
    # -------------------------------------------------------------------------

    @api.constrains('state')
    def _check_boq_before_approval(self):
        """Optimized: Single query for all records being approved"""
        boqs_to_check = self.filtered(lambda b: b.state == 'approved')
        if not boqs_to_check:
            return
            
        # Check all BOQs without lines in one go
        boqs_without_lines = boqs_to_check.filtered(lambda b: not b.boq_line_ids)
        if boqs_without_lines:
            raise ValidationError(_('BOQ cannot be approved without BOQ lines.'))

    @api.constrains('project_id', 'version', 'active')
    def _check_unique_active_version(self):
        """Optimized: Batch validation"""
        active_boqs = self.filtered('active')
        if not active_boqs:
            return
            
        # Get all unique project-version combinations
        project_version_pairs = [
            (boq.project_id.id, boq.version) 
            for boq in active_boqs
        ]
        
        # Check for duplicates in batch
        for project_id, version in project_version_pairs:
            duplicate_count = self.search_count([
                ('project_id', '=', project_id),
                ('version', '=', version),
                ('active', '=', True),
                ('id', 'in', active_boqs.ids)
            ])
            if duplicate_count > 1:
                raise ValidationError(_('An active BOQ with this version already exists for this project.'))

    def _check_one_active_boq(self):
        """Optimized: Single query for all records"""
        if not self:
            return
            
        # Get all project IDs
        project_ids = self.mapped('project_id').ids
        if not project_ids:
            return
            
        # Check for existing active BOQs in one query
        existing_boqs = self.search([
            ('project_id', 'in', project_ids),
            ('state', 'in', ['approved', 'locked']),
            ('id', 'not in', self.ids),
            ('active', '=', True)
        ])
        
        if existing_boqs:
            # Group by project for error message
            project_names = existing_boqs.mapped('project_id.name')
            raise ValidationError(
                _('There is already an active (Approved or Locked) BOQ for project(s): %s. Please revise the existing one.') % 
                ', '.join(project_names)
            )


class ConstructionBOQSection(models.Model):
    _name = 'construction.boq.section'
    _description = 'BOQ Section'
    _order = 'sequence, id'

    name = fields.Char(string='Section Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)


class ConstructionBOQLine(models.Model):
    _name = 'construction.boq.line'
    _description = 'BOQ Line Item'
    _order = 'sequence, id'

    boq_id = fields.Many2one('construction.boq', string='BOQ Reference', required=True, ondelete='cascade', index=True)
    section_id = fields.Many2one('construction.boq.section', string='Section')
    product_id = fields.Many2one('product.product', string='Product', domain="[('company_id', 'in', (company_id, False))]")
    task_id = fields.Many2one('project.task', string='Task', domain="[('project_id', '=', parent.project_id)]")
    activity_code = fields.Char(string='Activity Code', help="Code used to link this BOQ line to a specific project task or schedule activity.")
    company_id = fields.Many2one('res.company', related='boq_id.company_id', string='Company', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency', readonly=True)
    sequence = fields.Integer(string='Sequence', default=10)
    display_type = fields.Selection([('line_section', 'Section'), ('line_note', 'Note')], default=False)
    name = fields.Char(string='Description', required=True)
    description = fields.Text(string='Long Description')
    cost_type = fields.Selection([
        ('material', 'Material'), 
        ('labor', 'Labor'), 
        ('subcontract', 'Subcontract'), 
        ('service', 'Service'), 
        ('overhead', 'Overhead')
    ], string='Cost Type', required=True, default='material', help="Classifies the type of cost for reporting and analysis.")
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    estimated_rate = fields.Monetary(string='Rate', currency_field='currency_id', default=0.0, required=True)
    budget_amount = fields.Monetary(string='Budget Amount', compute='_compute_budget_amount', currency_field='currency_id', store=True)
    expense_account_id = fields.Many2one('account.account', string='Expense Account', required=True, check_company=True)
    analytic_account_id = fields.Many2one('account.analytic.account', related='boq_id.analytic_account_id', string='Analytic Account', store=True)
    analytic_distribution = fields.Json(string='Analytic Distribution', help="Distribute costs across multiple analytic accounts.")
    analytic_precision = fields.Integer(store=False, default=2)
    consumed_quantity = fields.Float(string='Consumed Qty', compute='_compute_consumption', store=True)
    consumed_amount = fields.Monetary(string='Consumed Amount', compute='_compute_consumption', currency_field='currency_id', store=True)
    remaining_quantity = fields.Float(string='Remaining Qty', compute='_compute_consumption', store=True)
    remaining_amount = fields.Monetary(string='Remaining Amount', compute='_compute_consumption', currency_field='currency_id', store=True)
    allow_over_consumption = fields.Boolean(string='Allow Over Consumption', default=False, help="If checked, allows consumption to exceed the budgeted quantity/amount without error.")
    consumption_ids = fields.One2many('construction.boq.consumption', 'boq_line_id', string='Consumptions')
    consumption_percentage = fields.Float(string='Progress', compute='_compute_consumption_percentage', store=False, help="Percentage of budget consumed.")

    @api.depends('quantity', 'estimated_rate')
    def _compute_budget_amount(self):
        for rec in self:
            rec.budget_amount = rec.quantity * rec.estimated_rate

    @api.depends('quantity', 'budget_amount', 'consumption_ids.quantity', 'consumption_ids.amount')
    def _compute_consumption(self):
        """Optimized: Single approach for all records with batch query"""
        # Initialize all records first
        for rec in self:
            rec.consumed_quantity = 0.0
            rec.consumed_amount = 0.0
            rec.remaining_quantity = rec.quantity
            rec.remaining_amount = rec.budget_amount
        
        # Separate new records (NewIds) and persisted records
        new_records = self.filtered(lambda r: not isinstance(r.id, int))
        real_records = self - new_records
        
        # Handle new records (in memory)
        for rec in new_records:
            if rec.consumption_ids:
                c_qty = sum(rec.consumption_ids.mapped('quantity'))
                c_amt = sum(rec.consumption_ids.mapped('amount'))
                rec.consumed_quantity = c_qty
                rec.consumed_amount = c_amt
                rec.remaining_quantity = rec.quantity - c_qty
                rec.remaining_amount = rec.budget_amount - c_amt
        
        # Handle persisted records with batch query
        if real_records:
            # Single query for all consumption data
            data = self.env['construction.boq.consumption'].read_group(
                [('boq_line_id', 'in', real_records.ids)],
                ['boq_line_id', 'quantity', 'amount'],
                ['boq_line_id']
            )
            
            # Create mapping for quick access
            data_map = {d['boq_line_id'][0]: d for d in data}
            
            # Update records with consumption data
            for rec in real_records:
                group = data_map.get(rec.id)
                if group:
                    c_qty = group['quantity']
                    c_amt = group['amount']
                    rec.consumed_quantity = c_qty
                    rec.consumed_amount = c_amt
                    rec.remaining_quantity = rec.quantity - c_qty
                    rec.remaining_amount = rec.budget_amount - c_amt

    @api.depends('consumed_amount', 'budget_amount')
    def _compute_consumption_percentage(self):
        for rec in self:
            if rec.budget_amount > 0:
                rec.consumption_percentage = (rec.consumed_amount / rec.budget_amount)
            else:
                rec.consumption_percentage = 0.0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.name = self.product_id.name
            self.description = self.product_id.description_sale or self.product_id.name
            self.uom_id = self.product_id.uom_id
            self.estimated_rate = self.product_id.standard_price
            account = self.product_id.property_account_expense_id or self.product_id.categ_id.property_account_expense_categ_id
            if not account:
                raise UserError(_("No Expense Account defined for product '%s'.") % self.product_id.name)
            self.expense_account_id = account.id

    @api.onchange('task_id')
    def _onchange_task_id(self):
        if self.task_id and self.task_id.activity_code:
            self.activity_code = self.task_id.activity_code

    @api.constrains('analytic_account_id', 'boq_id')
    def _check_project_alignment(self):
        """Optimized: Filter only records that need checking"""
        records_to_check = self.filtered(
            lambda r: r.boq_id.analytic_account_id and r.analytic_account_id
        )
        for rec in records_to_check:
            if rec.boq_id.analytic_account_id != rec.analytic_account_id:
                raise ValidationError(_('BOQ Line analytic account must match the Project analytic account.'))

    def check_consumption(self, qty, amount):
        self.ensure_one()
        if not self.allow_over_consumption:
            if qty > self.remaining_quantity + 0.0001:
                 raise ValidationError(_('BOQ Quantity Exceeded for %s.') % self.name)
            if amount > self.remaining_amount + 0.01:
                 raise ValidationError(_('BOQ Budget Exceeded for %s.') % self.name)

    # -------------------------------------------------------------------------
    # PROPAGATE VERSIONING FROM LINE CHANGES - OPTIMIZED
    # -------------------------------------------------------------------------
    
    @api.model_create_multi
    def create(self, vals_list):
        """Optimized: Batch processing of BOQ revisions"""
        # Extract all BOQ IDs in one pass
        boq_ids = {
            vals['boq_id'] for vals in vals_list 
            if vals.get('boq_id')
        }
        
        if boq_ids and not self.env.context.get('revision_copy'):
            # Get BOQs that need revision in one query
            boqs = self.env['construction.boq'].browse(list(boq_ids))
            boqs.filtered(
                lambda b: b.state in ['submitted', 'approved', 'locked']
            ).create_revision_snapshot()

        return super(ConstructionBOQLine, self).create(vals_list)

    def write(self, vals):
        """Optimized: Batch processing of BOQ revisions"""
        if not self.env.context.get('revision_copy'):
            # Get unique BOQs in batch
            boqs = self.mapped('boq_id')
            boqs.filtered(
                lambda b: b.state in ['submitted', 'approved', 'locked']
            ).create_revision_snapshot()
            
        return super(ConstructionBOQLine, self).write(vals)

    def unlink(self):
        """Optimized: Batch processing of BOQ revisions"""
        if not self.env.context.get('revision_copy'):
            # Get unique BOQs in batch
            boqs = self.mapped('boq_id')
            boqs.filtered(
                lambda b: b.state in ['submitted', 'approved', 'locked']
            ).create_revision_snapshot()
            
        return super(ConstructionBOQLine, self).unlink()

    _sql_constraints = [
        ('chk_qty_positive', 'CHECK(quantity > 0)', 'Quantity must be positive.'),
        ('chk_amount_positive', 'CHECK(budget_amount >= 0)', 'Budget amount cannot be negative.'),
        ('uniq_boq_product_section_activity', 'unique(boq_id, section_id, product_id, activity_code)', 'Duplicate product in the same section/activity is not allowed.')
    ]


class ConstructionBOQConsumption(models.Model):
    _name = 'construction.boq.consumption'
    _description = 'BOQ Consumption Ledger'
    _order = 'date desc, id desc'

    boq_line_id = fields.Many2one('construction.boq.line', string='BOQ Line', required=True, ondelete='restrict', index=True)
    source_model = fields.Char(string='Source Model', required=True)
    source_id = fields.Integer(string='Source ID', required=True)
    quantity = fields.Float(string='Quantity Consumed')
    amount = fields.Monetary(string='Amount Consumed', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='boq_line_id.currency_id', store=True)
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)

    @api.model_create_multi
    def create(self, vals_list):
        """Optimized: Batch validation"""
        # Pre-fetch all lines in one query
        line_ids = {vals['boq_line_id'] for vals in vals_list if vals.get('boq_line_id')}
        lines = self.env['construction.boq.line'].browse(list(line_ids))
        line_map = {line.id: line for line in lines}
        
        for vals in vals_list:
            line_id = vals.get('boq_line_id')
            if line_id and line_id in line_map:
                line = line_map[line_id]
                qty = vals.get('quantity', 0.0)
                amt = vals.get('amount', 0.0)

                # Check limits if positive consumption is added
                if qty > 0 or amt > 0:
                    line.check_consumption(qty, amt)

        return super(ConstructionBOQConsumption, self).create(vals_list)

    def init(self):
        self.env.cr.execute("""
            REVOKE UPDATE, DELETE ON construction_boq_consumption FROM PUBLIC;
        """)