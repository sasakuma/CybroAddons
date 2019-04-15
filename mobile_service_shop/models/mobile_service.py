from datetime import datetime, date, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import Warning, UserError
import pytz


class MobileServiceShop(models.Model):

    _name = 'mobile.service'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Code', copy=False, default="New")
    person_name = fields.Many2one('res.partner', string="Customer Name", required=True,
                                  domain="[('customer','=','True')]")
    contact_no = fields.Char(related='person_name.mobile', string="Contact Number")
    email_id = fields.Char(related='person_name.email', string="Email")

    street = fields.Char(related='person_name.street', string="Address")
    street2 = fields.Char(related='person_name.street2', string="Address")
    city = fields.Char(related='person_name.city', string="Address")
    state_id = fields.Many2one(related='person_name.state_id', string="Address")
    zip = fields.Char(related='person_name.zip', string="Address")
    country_id = fields.Many2one(related='person_name.country_id', string="Address")

    brand_name = fields.Many2one('mobile.brand', string="Mobile Brand", required=True)
    is_in_warranty = fields.Boolean(
        'In Warranty', default=False,
        help="Specify if the product is in warranty.")

    warranty_number = fields.Char(string="Warranty No ", help="warranty details")

    re_repair = fields.Boolean(
        'Re-repair', default=False,
        help="Re-repairing.")

    imei_no = fields.Char(string="IMEI Number")

    model_name = fields.Many2one('brand.model', string="Model",required=True, domain="[('mobile_brand_name','=',brand_name)]")
    image_medium = fields.Binary(related='model_name.image_medium', store=True, attachment=True)
    date_request = fields.Date(string="Requested date", default=fields.Date.context_today)
    return_date = fields.Date(string="Return date", required=True)
    technicion_name = fields.Many2one('res.users', string="Technician Name",
                                      default=lambda self: self.env.user, required=True)
    service_state = fields.Selection([('draft', 'Draft'), ('assigned', 'Assigned'),
                                      ('completed', 'Completed'), ('returned', 'Returned'),
                                      ('not_solved', 'Not solved')],
                                     string='Service Status', default='draft', track_visibility='always')

    complaints_tree = fields.One2many('mobile.complaint.tree', 'complaint_id', string='Complaints Tree')

    product_order_line = fields.One2many('product.order.line', 'product_order_id', string='Parts Order Lines')

    internal_notes = fields.Text(string="Internal notes")
    invoice_count = fields.Integer(compute='_invoice_count', string='# Invoice', copy=False)
    invoice_ids = fields.Many2many("account.invoice", string='Invoices', compute="_get_invoiced", readonly=True, copy=False)

    first_payment_inv = fields.Many2one('account.invoice', copy=False)

    first_invoice_created = fields.Boolean(string="First Invoice Created", invisible=True, copy=False)

    journal_type = fields.Many2one('account.journal', 'Journal', invisible=True,
                                   default=lambda self: self.env['account.journal'].search([('code', '=', 'SERV')]))
    account_type = fields.Many2one('account.account', 'Account', invisible=True,
                                   default=lambda self: self.env['account.account'].search([('code', '=', 200110)]))

    @api.model
    def _default_picking_transfer(self):
        type_obj = self.env['stock.picking.type']
        company_id = self.env.context.get('company_id') or self.env.user.company_id.id
        types = type_obj.search([('code', '=', 'outgoing'), ('warehouse_id.company_id', '=', company_id)], limit=1)
        if not types:
            types = type_obj.search([('code', '=', 'outgoing'), ('warehouse_id', '=', False)])
        return types[:4]

    stock_picking_id = fields.Many2one('stock.picking', string="Picking Id")

    picking_transfer_id = fields.Many2one('stock.picking.type', 'Deliver To', required=True,
                                          default=_default_picking_transfer,
                                          help="This will determine picking type of outgoing shipment")

    @api.onchange('return_date')
    def check_date(self):
        if self.return_date != False:
            return_date_string = datetime.strptime(str(self.return_date), "%Y-%m-%d")
            request_date_string = datetime.strptime(str(self.date_request), "%Y-%m-%d")
            if return_date_string < request_date_string:
                raise UserError("Return date should be greater than requested date")

    @api.multi
    def approve(self):
        self.service_state = 'assigned'

    @api.multi
    def complete(self):
        self.service_state = 'completed'

    @api.multi
    def return_to(self):
        self.service_state = 'returned'

    @api.multi
    def not_solved(self):
        self.service_state = 'not_solved'

    @api.multi
    def action_send_mail(self):
        '''
        This function opens a window to compose an email, with the edi sale template message loaded by default
        '''
        self.ensure_one()
        ir_model_data = self.env['ir.model.data']
        try:
            template_id = ir_model_data.get_object_reference('mobile_service_shop', 'email_template_mobile_service')[1]
        except ValueError:
            template_id = False
        try:
            compose_form_id = ir_model_data.get_object_reference('mail', 'email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False
        ctx = {
            'default_model': 'mobile.service',
            'default_res_id': self.ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
        }
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }

    @api.multi
    def return_advance(self):
        inv_obj = self.env['account.invoice'].search([('origin', '=', self.name)])
        inv_ids = []
        for each in inv_obj:
            inv_ids.append(each.id)
        view_id = self.env.ref('account.invoice_form').id
        if inv_ids:
            if len(inv_ids) <= 1:
                value = {
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'account.invoice',
                    'view_id': view_id,
                    'type': 'ir.actions.act_window',
                    'name': 'Invoice',
                    'res_id': inv_ids and inv_ids[0]
                }
            else:
                value = {
                    'domain': str([('id', 'in', inv_ids)]),
                    'view_type': 'form',
                    'view_mode': 'tree,form',
                    'res_model': 'account.invoice',
                    'view_id': False,
                    'type': 'ir.actions.act_window',
                    'name': 'Invoice',
                    'res_id': inv_ids
                }

            return value
        else:
            raise UserError("No invoice created")

    @api.multi
    def _invoice_count(self):
        invoice_ids = self.env['account.invoice'].search([('origin', '=', self.name)])
        self.invoice_count = len(invoice_ids)

    @api.model
    def create(self, vals):
        vals['name'] = self.env['ir.sequence'].next_by_code('mobile.service')
        vals['service_state'] = 'draft'
        return super(MobileServiceShop, self).create(vals)

    @api.multi
    def unlink(self):
        for i in self:
            if i.service_state != 'draft':
                raise UserError(_('You cannot delete an assigned service request'))
            return super(MobileServiceShop, i).unlink()

    @api.multi
    def action_invoice_create_wizard(self):

        return {
            'name': _('Create Invoice'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mobile.invoice',
            'type': 'ir.actions.act_window',
            'target': 'new'
        }

    @api.multi
    def action_post_stock(self):
        flag = 0
        for order in self.product_order_line:
            if order.product_uom_qty > order.qty_stock_move:
                flag = 1
                pick = {
                    'picking_type_id': self.picking_transfer_id.id,
                    'partner_id': self.person_name.id,
                    'origin': self.name,
                    'location_dest_id': self.person_name.property_stock_customer.id,
                    'location_id': self.picking_transfer_id.default_location_src_id.id,
                }

                picking = self.env['stock.picking'].create(pick)
                self.stock_picking_id = picking.id
                self.picking_count = len(picking)
                moves = order.filtered(
                    lambda r: r.product_id.type in ['product', 'consu'])._create_stock_moves_transfer(picking)
                move_ids = moves._action_confirm()
                move_ids._action_assign()
            if order.product_uom_qty < order.qty_stock_move:
                raise UserError(_('Used quantity is less than quantity stock move posted. '))
        if flag != 1:
            raise UserError(_('Nothing to post stock move'))

    @api.multi
    def action_view_invoice(self):
        inv_obj = self.env['account.invoice'].search([('origin', '=', self.name)])
        inv_ids = []
        for each in inv_obj:
            inv_ids.append(each.id)
        view_id = self.env.ref('account.invoice_form').id

        if inv_ids:
            if len(inv_ids) <= 1:
                value = {
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'account.invoice',
                    'view_id': view_id,
                    'type': 'ir.actions.act_window',
                    'name': 'Invoice',
                    'res_id': inv_ids and inv_ids[0]
                }
            else:
                value = {
                    'domain': str([('id', 'in', inv_ids)]),
                    'view_type': 'form',
                    'view_mode': 'tree,form',
                    'res_model': 'account.invoice',
                    'view_id': False,
                    'type': 'ir.actions.act_window',
                    'name': 'Invoice',
                    'res_id': inv_ids
                }

            return value

    @api.multi
    def get_ticket(self):
        self.ensure_one()
        user = self.env['res.users'].browse(self.env.uid)
        if user.tz:
            tz = pytz.timezone(user.tz)
            time = pytz.utc.localize(datetime.now()).astimezone(tz)
            date_today = time.strftime("%Y-%m-%d %H:%M %p")
        else:
            date_today = datetime.strftime(datetime.now(), "%Y-%m-%d %I:%M:%S %p")
        complaint_text = ""
        description_text = ""
        complaint_id = self.env['mobile.complaint.tree'].search([('complaint_id', '=', self.id)])
        if complaint_id:
            for obj in complaint_id:
                complaint = obj.complaint_type_tree
                description = obj.description_tree
                complaint_text = complaint.complaint_type + ", " + complaint_text
                if description.description:
                    description_text = description.description + ", " + description_text
        else:
            for obj in complaint_id:
                complaint = obj.complaint_type_tree
                complaint_text = complaint.complaint_type + ", " + complaint_text
        data = {
            'ids': self.ids,
            'model': self._name,
            'date_today': date_today,
            'date_request': self.date_request,
            'date_return': self.return_date,
            'sev_id': self.name,
            'warranty': self.is_in_warranty,
            'customer_name': self.person_name.name,
            'imei_no': self.imei_no,
            'technician': self.technicion_name.name,
            'complaint_types': complaint_text,
            'complaint_description': description_text,
            'mobile_brand': self.brand_name.brand_name,
            'model_name': self.model_name.mobile_brand_models,


        }
        return self.env.ref('mobile_service_shop.mobile_service_ticket').report_action(self, data=data)


class MobileBrand(models.Model):

    _name = 'mobile.brand'
    _rec_name = 'brand_name'

    brand_name = fields.Char(string="Mobile Brand", required=True)


class MobileComplaintType(models.Model):

    _name = 'mobile.complaint'
    _rec_name = 'complaint_type'

    complaint_type = fields.Char(string="Complaint Type", required=True)


class MobileComplaintTypeTemplate(models.Model):

    _name = 'mobile.complaint.description'
    _rec_name = 'description'

    complaint_type_template = fields.Many2one('mobile.complaint', string="Complaint Type Template", required=True)
    description = fields.Text(string="Complaint Description")


class MobileComplaintTree(models.Model):

    _name = 'mobile.complaint.tree'
    _rec_name = 'complaint_type_tree'

    complaint_id = fields.Many2one('mobile.service')

    complaint_type_tree = fields.Many2one('mobile.complaint', string="Category", required=True)
    description_tree = fields.Many2one('mobile.complaint.description', string="Description",
                                       domain="[('complaint_type_template','=',complaint_type_tree)]")


class MobileBrandModels(models.Model):

    _name = 'brand.model'
    _rec_name = 'mobile_brand_models'

    mobile_brand_name = fields.Many2one('mobile.brand', string="Mobile Brand", required=True)
    mobile_brand_models = fields.Char(string="Model Name", required=True)
    image_medium = fields.Binary(string='image', store=True, attachment=True)


class MobileServiceTermsAndConditions(models.Model):

    _name = 'terms.conditions'
    _rec_name = 'terms_id'

    terms_id = fields.Char(String="Terms and condition", compute="_find_id")
    terms_conditions = fields.Text(string="Terms and Conditions")

    def _find_id(self):
        self.terms_id = self.id or ''


class ProductProduct(models.Model):
    _inherit = 'product.template'

    is_a_parts = fields.Boolean(
        'Is a Mobile Part', default=False,
        help="Specify if the product is a mobile part or not.")

    brand_name = fields.Many2one('mobile.brand', String="Brand", help="Select a mobile brand for the part")
    model_name = fields.Many2one('brand.model', String="Model Name", domain="[('mobile_brand_name','=',brand_name)]",
                                 help="Select a model for the part")
    model_colour = fields.Char(string="Colour", help="colour for the part")
    extra_descriptions = fields.Text(string="Note")


class ProductOrderLine(models.Model):
    _name = 'product.order.line'

    product_order_id = fields.Many2one('mobile.service')

    product_id = fields.Many2one('product.product', string='Product',
                                 domain="[('is_a_parts','=', True)]")
    product_uom_qty = fields.Float(string='Used Quantity', default=1.0)
    price_unit = fields.Float(string='Unit Price', default=0.0)
    qty_invoiced = fields.Float(string='Invoiced qty', readonly=True)
    qty_stock_move = fields.Float(string='Stock Move Posted Qty', readonly=True)
    part_price = fields.Char(compute='_compute_amount', string='Price', readonly=True, store=True)
    product_uom = fields.Char(string='Unit of Measure')

    @api.onchange('product_id')
    def change_prod(self):
        self.ensure_one()
        if self.product_id:
            product_template_obj = self.product_id.product_tmpl_id
            self.price_unit = product_template_obj.list_price
            self.product_uom = product_template_obj.uom_id.name

    @api.depends('product_uom_qty', 'product_id')
    def _compute_amount(self):
        """
        Compute the amount
        """
        for line in self:
            price = line.price_unit * line.product_uom_qty

            line.update({
                'part_price': price,
            })

    def _create_stock_moves_transfer(self, picking):
        moves = self.env['stock.move']
        done = self.env['stock.move'].browse()
        if self.product_id.product_tmpl_id.type != 'service':
            price_unit = self.price_unit
            template = {
                'name': self.product_id.product_tmpl_id.name or '',
                'product_id': self.product_id.id,
                'product_uom': self.product_id.product_tmpl_id.uom_id.id,
                'location_id': picking.picking_type_id.default_location_src_id.id,
                'location_dest_id': self.product_order_id.person_name.property_stock_customer.id,
                'picking_id': picking.id,
                'move_dest_id': False,
                'state': 'draft',
                'company_id': self.product_order_id.account_type.company_id.id,
                'price_unit': price_unit,
                'picking_type_id': picking.picking_type_id.id,
                'procurement_id': False,
                'route_ids': 1 and [
                    (6, 0, [x.id for x in self.env['stock.location.route'].search([('id', 'in', (2, 3))])])] or [],
                'warehouse_id': picking.picking_type_id.warehouse_id.id,
            }
            qty = self.product_uom_qty - self.qty_stock_move
            diff_quantity = qty
            tmp = template.copy()
            tmp.update({
                'product_uom_qty': diff_quantity,
            })
            template['product_uom_qty'] = diff_quantity
            done += moves.create(template)
            self.qty_stock_move = self.qty_stock_move + qty
        return done
