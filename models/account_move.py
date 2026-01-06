# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # [cite_start]Sub-step: Add field boq_line_id [cite: 79]
    boq_line_id = fields.Many2one(
        'construction.boq.line', 
        string='BOQ Item', 
        index=True,
        domain="[('boq_id.state', 'in', ('approved', 'locked'))]",
        help="Link this invoice line to a BOQ line for cost tracking."
    )

    # Sub-step: Auto-populate boq_line_id from Purchase Order Line
    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to automatically pull the BOQ Line from the linked Purchase Order Line.
        This ensures that when 'Create Bill' is clicked on a PO, the BOQ reference is preserved.
        """
        for vals in vals_list:
            # If this line is linked to a PO line and no BOQ line is manually set
            if vals.get('purchase_line_id') and not vals.get('boq_line_id'):
                po_line = self.env['purchase.order.line'].browse(vals['purchase_line_id'])
                if po_line.boq_line_id:
                    vals['boq_line_id'] = po_line.boq_line_id.id
        
        return super(AccountMoveLine, self).create(vals_list)

    @api.onchange('purchase_line_id')
    def _onchange_purchase_line_id_boq(self):
        """
        Handle UI updates when a user manually selects a PO line on a Vendor Bill.
        """
        if self.purchase_line_id and self.purchase_line_id.boq_line_id:
            self.boq_line_id = self.purchase_line_id.boq_line_id