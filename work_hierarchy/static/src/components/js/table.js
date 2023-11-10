/* @odoo-module */

import { MessageBrokerComponent } from "@work_hierarchy/components/js/base";
import { Line } from "@work_hierarchy/components/js/line"
import { useSubEnv } from "@odoo/owl"

export class Table extends MessageBrokerComponent {
    setup() {
        super.setup()
        this.data = this.props.data
        this.header = this.props.header
        this.env.data = this.data.hierarchy_data;
        this.env.isManager = this.data.manager;
        useSubEnv(this.env)
    }
    mounted(){
        let res = super.mounted();

        return res
    }

}

Table.components = { Line };
Table.template = "work_hierarchy.hierarchy_table";
