/** @odoo-module **/


import { Component, onMounted, onWillStart} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

import { registry } from "@web/core/registry";


export class TaskDependency extends Component {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        onMounted(async () => {
            await this.mounted();
        })
        onWillStart(async () => {
            await this.willStart();
        })
        this.displayOption = {};
        // useSubEnv({
        //     'onClickViewButton': this.onClickViewButton.bind(this)
        // })
    }

    async willStart() {
        this.loadFile('/work_abc_management/static/public/js/dependency.js')
        // let response = await this.orm.call(
        //     this.props.action.context.model,
        //     'launch_dependency',
        //     [this.props.action.context.task_ids],
        //     {
        //         context: this.props.action.context
        //     }
        // );
        // this.data = response
    }
}
TaskDependency.template = "work_abc_management.Dependencies"


registry.category("actions").add("task_dependency", TaskDependency);
