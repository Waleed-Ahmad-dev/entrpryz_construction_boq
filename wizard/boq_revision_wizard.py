# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class ConstructionBOQRevisionWizard(models.TransientModel):
    _name = 'construction.boq.revision.wizard'
    _description = 'BOQ Revision Wizard'

    boq_id = fields.Many2one('construction.boq', string='BOQ', required=True, readonly=True)
    revision_reason = fields.Text(string='Reason for Revision', required=True, 
                                    help="Please provide a detailed reason for creating a new version of this BOQ.")

    def action_create_revision(self):
        """
        Trigger the revision logic defined in the history model.
        """
        self.ensure_one()
        
        # Call the business logic in the persistent model to clone the BOQ
        # and ensure the original remains immutable.
        revision_record = self.env['construction.boq.revision'].create_revision(
            self.boq_id.id, 
            self.revision_reason
        )

        # Redirect the user to the NEW (Draft) BOQ
        return {
            'type': 'ir.actions.act_window',
            'name': _('Revised BOQ'),
            'res_model': 'construction.boq',
            'res_id': revision_record.new_boq_id.id,
            'view_mode': 'form',
            'target': 'current',
        }