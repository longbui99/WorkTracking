/** @odoo-module **/

import { useRef } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";

import { Table } from "@work_hierarchy/components/js/table"
import { Header } from "@work_hierarchy/components/js/header"
import { MessageBrokerComponent } from "@work_hierarchy/components/js/base";

export class App extends MessageBrokerComponent {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.data = [];
        this.header = [];
        this.currency = {};
        this.displayName = 'Work Hierarchy';
        this.tableRef = useRef('TableRef');
        this.controlPanelDisplay = {
            "bottom-left": false,
            "bottom-right": false,
            "top-right": false
        };
    }

}

App.components = {
    Header, 
    ControlPanel };
App.template = "work_hierarchy.hierarchy_app";
