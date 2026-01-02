# -*- coding: utf-8 -*-
{
     'name': 'Entrpryz Construction BOQ Control',
     'version': '1.0',
     'category': 'Construction/Project Management',
     'summary': 'Construction BOQ, Budget Control, and Project Costing',
     'description': """
          Entrpryz Construction BOQ Control Module
          ========================================
          Implements tight control over project cost consumption via formal BOQ.
          
          Key Features:
          - Formal BOQ as budget authority
          - Tight control over project cost consumption
          - Clear linkage between BOQ, procurement, inventory, accounting, and billing
          - Accurate budget vs actual and project profitability reporting
          - Support for BOQ revisions and variations
     """,
     'author': 'ELB Marketing & Developers',
     'website': 'https://www.entrpryz.com',
     'depends': [
          'base',
          'project',
          'analytic',
          'purchase',
          'stock',
          'account',
     ],
     'data': [
          'security/ir.model.access.csv',
          'views/boq_views.xml',
     ],
     'installable': True,
     'application': True,
     'license': 'LGPL-3',
}