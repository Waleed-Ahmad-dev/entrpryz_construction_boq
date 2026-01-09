# models/boq_revision.py
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ConstructionBOQRevision(models.Model):
    _name = 'construction.boq.revision'
    _description = 'BOQ Revision History'
    _order = 'create_date desc'

    original_boq_id = fields.Many2one('construction.boq', string='Original BOQ (Snapshot)', required=True, readonly=True, ondelete='restrict')
    new_boq_id = fields.Many2one('construction.boq', string='New BOQ (Current)', required=True, readonly=True, ondelete='cascade')
    revision_reason = fields.Text(string='Reason for Revision', required=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    approval_date = fields.Date(string='Approval Date', readonly=True)
    
    # We rely on construction.boq to handle the logic. 
    # This model simply stores the history link.