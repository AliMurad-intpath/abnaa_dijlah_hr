from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_employee_no = fields.Char('Employee number', copy=False, index=True, tracking=True)
    ad_first_name = fields.Char('First name')
    ad_mid_name = fields.Char("Father's name")
    ad_last_name = fields.Char("Grandfather's name")
    ad_surname = fields.Char('Surname')
    ad_mother_name = fields.Char("Mother's name")
    ad_previous_job = fields.Char('Previous job')
    ad_work_site_id = fields.Many2one('ad.work.site', string='Work site', tracking=True)
    ad_work_governorate = fields.Char(related='ad_work_site_id.governorate', string='Work governorate')
    ad_work_area = fields.Char(related='ad_work_site_id.area', string='Work area')
    ad_res_governorate = fields.Char('Governorate')
    ad_res_district = fields.Char('District - sub-district')
    ad_neighborhood = fields.Char('Neighborhood')
    ad_mahalla = fields.Char('Neighborhood (Mahalla)')
    ad_alley = fields.Char('Alley')
    ad_house = fields.Char('House')
    ad_landmark = fields.Char('Nearest landmark')
    ad_address = fields.Char('Residential address', compute='_compute_ad_address')
    ad_resid_issuer = fields.Char('Residence card - issuing authority')
    ad_resid_no = fields.Char('Residence card - number')
    ad_resid_date = fields.Date('Residence card - issue date')
    ad_ration_center = fields.Char('Ration card - center name')
    ad_ration_no = fields.Char('Ration card - number')
    ad_ration_date = fields.Date('Ration card - issue date')
    ad_civil_issuer = fields.Char('Civil status ID - issuing authority')
    ad_civil_record_no = fields.Char('Civil status ID - record number')
    ad_civil_page_no = fields.Char('Civil status ID - page number')
    ad_nat_issuer = fields.Char('Nationality certificate - issuing authority')
    ad_nat_wallet_no = fields.Char('Nationality certificate - folder number')
    ad_nat_date = fields.Date('Nationality certificate - issue date')
    ad_passport_issuer = fields.Char('Passport - issuing authority')
    ad_passport_no = fields.Char('Passport - number')
    ad_passport_date = fields.Date('Passport - issue date')
    ad_moi_code = fields.Char('Code')
    ad_moi_emp_no = fields.Char('Employee number')
    ad_moi_company_code = fields.Char('Company numeric code')
    ad_moi_jk_no = fields.Char('JK number')
    ad_moi_file_no = fields.Char('File number - ID')

    @api.depends('ad_res_governorate', 'ad_res_district', 'ad_neighborhood', 'ad_mahalla', 'ad_alley', 'ad_house')
    def _compute_ad_address(self):
        for emp in self:
            parts = [emp.ad_res_governorate, emp.ad_res_district, emp.ad_neighborhood, emp.ad_mahalla,
                     emp.ad_alley and 'ز %s' % emp.ad_alley, emp.ad_house and 'د %s' % emp.ad_house]
            emp.ad_address = ' / '.join(p for p in parts if p)

    @api.onchange('name')
    def _onchange_name_split(self):
        for emp in self:
            if emp.name and not (emp.ad_first_name or emp.ad_mid_name or emp.ad_last_name):
                parts = emp.name.split()
                emp.ad_first_name = parts[0] if parts else False
                emp.ad_mid_name = parts[1] if len(parts) > 1 else False
                emp.ad_last_name = parts[2] if len(parts) > 2 else False
                emp.ad_surname = ' '.join(parts[3:]) if len(parts) > 3 else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('ad_employee_no'):
                vals['ad_employee_no'] = self.env['ir.sequence'].next_by_code('ad.hr.employee.no')
        return super().create(vals_list)
