odoo.define('project_management.DownloadFile', function (require) {
    "use strict";

    var core = require('web.core');
    var _t = core._t;
    var widgetRegistry = require('web.widget_registry');
    var Widget = require('web.Widget');

    const framework = require('web.framework');
    const session = require('web.session');

    var Perform2CountButton = Widget.extend({
        tagName: 'button',
        className: 'btn btn-primary o_validation',
        events: {
            'click': '_executeAction',
        },
        init: function (parent, record, options={}) {
            this._super.apply(this, arguments);
            this.parent = parent;
            this.recordData = record;
            this.attrs = options.attrs;
        },
        start: function () {
            this._super.apply(this, arguments);
            this.$el.text(_t(this.attrs.string || 'Export'));
        },
        _executeAction: function(){
            let self = this;
            framework.blockUI();
            session.get_file({
                url: '/lb-project-management/export',
                data: {
                    data: JSON.stringify({
                        "model": self.recordData.model,
                        "res_id": self.recordData.res_id,
                        "method": self.attrs.call_method
                    })
                },
                complete: framework.unblockUI,
            });
        }
    });

    widgetRegistry.add('export_button', Perform2CountButton);

    return Perform2CountButton;

});
