# -*- coding: utf-8 -*-
from odoo import models, fields

class ConstructionBOQSection(models.Model):
    _name = 'construction.boq.section'
    _description = 'Global BOQ Section'
    _order = 'sequence, id'

    name = fields.Char(string='Section Name', required=True, translate=True)
    code = fields.Char(string='Code')
    description = fields.Text(string='Description')
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'The section name must be unique!')
    ]