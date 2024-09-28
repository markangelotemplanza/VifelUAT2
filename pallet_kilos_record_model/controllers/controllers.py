# -*- coding: utf-8 -*-
# from odoo import http


# class PalletKilosRecordModel(http.Controller):
#     @http.route('/pallet_kilos_record_model/pallet_kilos_record_model', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/pallet_kilos_record_model/pallet_kilos_record_model/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('pallet_kilos_record_model.listing', {
#             'root': '/pallet_kilos_record_model/pallet_kilos_record_model',
#             'objects': http.request.env['pallet_kilos_record_model.pallet_kilos_record_model'].search([]),
#         })

#     @http.route('/pallet_kilos_record_model/pallet_kilos_record_model/objects/<model("pallet_kilos_record_model.pallet_kilos_record_model"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('pallet_kilos_record_model.object', {
#             'object': obj
#         })

