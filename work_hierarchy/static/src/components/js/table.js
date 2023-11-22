/* @odoo-module */

import { MessageBrokerComponent } from "@work_hierarchy/components/js/base";
import { Line } from "@work_hierarchy/components/js/line"
import { getStorage } from "@work_hierarchy/components/js/base";

export class Table extends MessageBrokerComponent {
    setup() {
        super.setup()
        let payload = getStorage(this.env.storage);
        this.headers = payload.headers;
        this.initialNodes = payload.initial_nodes;
    }
}

Table.components = { Line };
Table.template = "work_hierarchy.hierarchy_table";
