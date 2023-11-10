/** @odoo-module **/

import { registry } from "@web/core/registry";
import { App as HierarchyApp } from "@work_hierarchy/components/js/app"


export class AllocationBusyRates extends HierarchyApp {
    setup(){
        super.setup();
        this.key = 'AllocationBusyRate';
        this.tableClass = Table;
        this.displayName = 'Allocation Busy Rates';
        this.params = []
    }
    async willStart() {
        let res = super.willStart();
        const proms = [];
        proms.push(
            res,
            this._getData(),
            this._getHeader()
        );
        return Promise.all(proms);
    }

    getLocalVersion(){
        // return localStorage.getItem(this.env.localName)
    }

    setLocalVersion(version_id){
        // localStorage.setItem(this.env.localName, version_id)
    }

    async _getData() {
        let version_id = this.props.action.context?.version_id || this.props.action.params?.active_id;
        if (!version_id){
            version_id = parseInt(this.getLocalVersion());
        }
        this.setLocalVersion(version_id)
        this.context.model
        let response = await this.orm.call(
            this.context.model,
            'launch_report',
            this.params
        );
        this.data = response.body;
        this.header = response.header;
    }

    reloadPage(data){
        this.table.destroy();
        this.data = data;
        this.mountTable();
        if (this.data.header?.version_id){
            this.setLocalVersion(this.data.header.record_id);
        }
    }

    mounted(){
        let res = super.mounted();
        this.mountTable();
        return res
    }

    mountTable(){
        this.table = new this.tableClass(this, {
            'data': this.data,
            'header': this.header,
            'currency': this.currency
        })
        this.table.mount(this.tableRef.el);
    }

}


registry.category("actions").add("allocation_busy_rate", AllocationBusyRates);
