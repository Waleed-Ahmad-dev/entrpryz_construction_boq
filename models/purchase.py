# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # Added project_id to header to filter BOQ lines
    project_id = fields.Many2one('project.project', string='Project')


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    boq_line_id = fields.Many2one(
        'construction.boq.line', 
        string='BOQ Item', 
        index=True,
        domain="[('boq_id.state', 'in', ('approved', 'locked'))]"
    )

    # Sub-step: Domain logic (Dynamic domain based on Project)
    # Note: We also handle this in the XML view for better UI experience, 
    # but this onchange helps clean up if the project changes.
    @api.onchange('boq_line_id')
    def _onchange_boq_line_id(self):
        if self.boq_line_id:
            # Auto-fill product and UoM from BOQ if empty
            if not self.product_id:
                self.product_id = self.boq_line_id.product_id
            if not self.product_uom:
                self.product_uom = self.boq_line_id.uom_id
            # Optional: Set analytic distribution based on BOQ line
            if self.boq_line_id.analytic_distribution:
                self.analytic_distribution = self.boq_line_id.analytic_distribution

    # Sub-step: Validation Constraint
    @api.constrains('product_qty', 'boq_line_id')
    def _check_boq_limit(self):
        for line in self:
            if line.boq_line_id and line.state in ('draft', 'sent'):
                # [cite_start]Check 1: Quantity Limit [cite: 71]
                if not line.boq_line_id.allow_over_consumption:
                    # We compare against remaining quantity. 
                    # Note: In a real scenario, you might subtract current PO line qty to avoid double counting during updates,
                    # but per strict prompt requirements:
                    if line.product_qty > line.boq_line_id.remaining_quantity:
                        raise ValidationError(
                            _('Purchase Quantity (%s) exceeds BOQ Remaining Quantity (%s) for item %s.') % (
                                line.product_qty, 
                                line.boq_line_id.remaining_quantity,
                                line.boq_line_id.name
                            )
                        )
                
                # [cite_start]Check 2: Project Alignment [cite: 73]
                if line.order_id.project_id and line.boq_line_id.boq_id.project_id != line.order_id.project_id:
                    raise ValidationError(_('The BOQ Line selected does not belong to the Project on the Purchase Order.'))