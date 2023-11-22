/** @odoo-module **/

import { registry } from "@web/core/registry";
import { App as HierarchyApp } from "@work_hierarchy/components/js/app"


export class AllocationBusyRates extends HierarchyApp {
    setup(){
        super.setup();
        this.key = 'AllocationBusyRate';
        this.displayName = 'Allocation Busy Rates';
        this.params = []
    }

    getLocalVersion(){
        // return localStorage.getItem(this.env.localName)
    }

    setLocalVersion(version_id){
        // localStorage.setItem(this.env.localName, version_id)
    }


    reloadPage(data){
        this.table.destroy();
        this.data = data;
        this.mountTable();
        if (this.data.header?.version_id){
            this.setLocalVersion(this.data.header.record_id);
        }
    }

}


registry.category("actions").add("allocation_busy_rate", AllocationBusyRates);
