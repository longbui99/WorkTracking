/** @odoo-module **/

import { useRef, onMounted, onWillStart, useSubEnv, useState} from "@odoo/owl"
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { ViewButton } from "@web/views/view_button/view_button";

import { Table } from "@work_hierarchy/components/js/table"
import { MessageBrokerComponent } from "@work_hierarchy/components/js/base";
import { setStorage } from "@work_hierarchy/components/js/base";

export class App extends MessageBrokerComponent {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.displayName = 'Work Hierarchy';
        this.tableRef = useRef('TableRef');
        this.tableClass = Table;
        this.controlPanelDisplay = {
            "bottom-left": false,
            "bottom-right": false,
            "top-right": false
        };
        onMounted(async()=>{
            // await this.mounted()
        })
        onWillStart(async ()=>{
            await this.willStart()
        })
        this.displayOption = {};
        useSubEnv({
            'onClickViewButton': this.onClickViewButton.bind(this)
        })
        this.state = useState({
            'data_version': 1
        })

        
    }

    async onClickViewButton(params){
        let response = await this.orm.call(
            this.props.action.context.model,
            'action_click_header_button',
            [],
            params.clickParams.kwargs
        );
        if (response?.arch){
            this.arch = response.arch;
            setStorage(this.env.storage, response);
            this.render(true)
        }
    }

    get display() {
        const { controlPanel } = this.displayOption;
        return {
            ...this.displayOption,
            controlPanel: {
                ...controlPanel,
                layoutActions: true,
            },
        };
    }
    
    async willStart() {
        const proms = [];
        proms.push(
            this._getData()
        );
        return Promise.all(proms);
    }
    
    async _getData() {
        let response = await this.orm.call(
            this.props.action.context.model,
            'launch_report',
            this.params
        );
        this.arch = response.arch;
        setStorage(this.env.storage, response)
    }


}

App.components = {
    Table,
    Layout,
    ViewButton };
App.template = "work_hierarchy.hierarchy_app";
