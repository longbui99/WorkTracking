from lxml import html

def template_to_markup(env, template, **kwargs):
    return env['ir.qweb'].sudo()._render(
        html.fragment_fromstring(template['arch']),
        kwargs,
    )
