
const queryString = window.location.search;
const urlParams = new URLSearchParams(queryString);

let netloc = window.location.origin
let fetchData = `${netloc}/web/planning/dependencies/fetch/${urlParams.get('key')}`

fetch(fetchData, {
    method: "POST",
    headers: {
        "Content-Type": "application/json",
    },
    body: JSON.stringify({})
}).then(async result => {
    let json = await result.json()
    let payload = json.result;
    launch(payload)
})

import React, { useCallback, useState } from "https://cdn.jsdelivr.net/npm/react@18.2.0/+esm";
import ReactDOM from "https://cdn.jsdelivr.net/npm/react-dom@18.2.0/+esm";
import ReactFlow, {
    Controls,
    Background,
    applyEdgeChanges,
    applyNodeChanges,
    Handle,
    Position,
    MarkerType
} from "https://cdn.jsdelivr.net/npm/reactflow@11.7.4/+esm";



function launch(node_hierarchy) {

    class Geo {
        constructor() {
            this.column = 0;
            this.row = 0;
            this.x = 0;
            this.y = 0
        }
    }
    class Node {
        constructor(key, values) {
            this.key = key;
            this.position = new Geo();
            this.children_keys = values.children;
            this.parent_keys = [];
            this.level = 0;
            this.datas = values.datas;
        }
    }

    class Nodes {
        constructor(values) {
            this.key_vals = {};
            this.nodes = []
            for (let key in values) {
                let value = values[key];
                let node = new Node(key, value)
                this.key_vals[node.key] = node
                this.nodes.push(node)
            }
        }

        get(key) {
            return this.key_vals[key]
        }

        length() {
            return this.key_vals.length;
        }
        iter() {
            return this.nodes
        }

        setParent(datas) {
            for (let node of this.nodes) {
                for (let child_key of node.children_keys) {
                    datas.get(child_key).parent_keys.push(node.key)
                }
            }
            return this;
        }

        getInitialNodes() {
            let initialNodes = [];
            for (let node of this.nodes) {
                if (!node.parent_keys.length) {
                    initialNodes.push(node.key)
                }
            }
            return initialNodes
        }

        enterNodeLevel() {
            this.nodeByLevel = {};
            for (let node of this.nodes) {
                if (!(node.level in this.nodeByLevel)) {
                    this.nodeByLevel[node.level] = [];
                }
                this.nodeByLevel[node.level].push(node);
            }
        }

        getLevelNodes(level) {
            return this.nodeByLevel[level]
        }

        getMaxNbrNodeOnLevel() {
            let maxNodes = 0
            for (let key in this.nodeByLevel) {
                if (this.nodeByLevel[key].length > maxNodes) {
                    maxNodes = this.nodeByLevel[key].length;
                }
            }
            return maxNodes
        }

    }

    let nodes = new Nodes(node_hierarchy)

    let initialNodes = nodes.setParent(nodes).getInitialNodes(nodes)

    function recursiveSetLevel(level, travelNodes) {
        for (let nodeKey of travelNodes) {
            let node = nodes.get(nodeKey);
            if (node.level < level) {
                node.level = level;
            }
            recursiveSetLevel(level + 1, node.children_keys)
        }
    }
    recursiveSetLevel(0, initialNodes)


    nodes.enterNodeLevel()
    let maxNodes = nodes.getMaxNbrNodeOnLevel()
    let maxLevel = 0
    for (let node of nodes.iter()) {
        if (maxLevel < node.level) {
            maxLevel = node.level;
        }
    }

    let matrix = []
    for (let row = 0; row < maxLevel + 1; row++) {
        let row = []
        for (let i = 0; i < maxNodes; i++) {
            row.push(0)
        }
        matrix.push(row)
    }

    for (let level = 0; level < maxLevel + 1; level++) {
        let levelNodes = nodes.getLevelNodes(level);
        let padding = parseInt(maxNodes / levelNodes.length);
        let step_data = matrix[level];
        let index = 0;
        for (let node of levelNodes) {
            step_data[index] = node.key
            node.position.row = level;
            node.position.column = index
            index += padding
        }
    }

    function recursiveGetLink(links, travelNodes) {
        for (let nodeKey of travelNodes) {
            let node = nodes.get(nodeKey);
            for (let childKey of node.children_keys) {
                let child = nodes.get(childKey);
                links.push([node.key, child.key])
            }
            recursiveGetLink(links, node.children_keys)
        }
    }
    let links = [];

    recursiveGetLink(links, initialNodes);

    var marginX = 400, marginY = 0;

    var nodeDatas = [];
    for (let node of nodes.iter()) {
        let type = "input";
        if (!node.children_keys.length) {
            type = "output;"
        }
        if (node.children_keys.length && node.parent_keys.length) {
            type = undefined;
        }
        nodeDatas.push({
            'id': node.key,
            type: 'customLBNode',
            'data': {
                'label': node.datas.task_key,
                'datas': node.datas
            },
            'position': {
                'x': node.position.row * 300 + marginX,
                'y': node.position.column * 100 + marginY
            },
            style: {
                width: 200,
                background: 'white'
            },
            dragging: false
        })
    }

    var linkDatas = [];
    for (let link of links) {
        linkDatas.push({
            'id': `e${link[0]}-${link[1]}`,
            'source': link[0],
            'target': link[1],
            'animated': true,
            markerEnd: {
                type: MarkerType.ArrowClosed,
            },
        })
    }


    let CustomNode = ({ data }) => {
        return (
            <>
                <div class="node-segment">
                    <div class="title">{data.datas.task_key}</div>
                    <div class="description" title={data.datas.task_name}>{data.datas.task_name}</div>
                    <div class="assignee" title={data.datas.assignee_id? data.datas.assignee_id[1]: ""}>{data.datas.assignee_id? data.datas.assignee_id[1]: "N/A"}</div>
                    <div class="addtional-description">{data.datas.story_point}</div>
                </div>
                <Handle type="target" position={Position.Left} />
                <Handle type="source" position={Position.Right} />
            </>
        );
    };

    const nodeTypes = { customLBNode: CustomNode };


    function Flow() {
        const [nodes, setNodes] = useState(nodeDatas);
        const [edges, setEdges] = useState(linkDatas);

        const onNodesChange = useCallback(
            (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
            [setNodes]
        );
        const onEdgesChange = useCallback(
            (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
            [setEdges]
        );

        return (
            <ReactFlow
                nodeTypes={nodeTypes}
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                fitView
            >
            // <Background />
            // <Controls />
            </ReactFlow>
        );
    }

    const App = () => {
        return (
            <Flow />
        );
    };

    ReactDOM.render(<App />, document.getElementById('app'));


}
