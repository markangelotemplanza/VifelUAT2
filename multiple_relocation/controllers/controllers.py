# -*- coding: utf-8 -*-
# from odoo import http


# class MultipleRelocation(http.Controller):
#     @http.route('/multiple_relocation/multiple_relocation', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/multiple_relocation/multiple_relocation/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('multiple_relocation.listing', {
#             'root': '/multiple_relocation/multiple_relocation',
#             'objects': http.request.env['multiple_relocation.multiple_relocation'].search([]),
#         })

#     @http.route('/multiple_relocation/multiple_relocation/objects/<model("multiple_relocation.multiple_relocation"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('multiple_relocation.object', {
#             'object': obj
#         })

