# Workflow 2.0 node/schema reference (experiment-local)

This is a standalone workspace Markdown file. Required permission: read=1,
write=4. The iterator reads this file at runtime and must not edit it.

## Authority and scope

- Current runtime declarations/schema and semantic checks below override stale
  examples in the repository skill. In particular, only listed node types exist;
  `wait_terminal_event` and `read_terminal_input` are not current node types.
- This catalog documents ALL runtime types, not permission to use them in main.
  `main_policy` marks the stricter evolution gate. Preserve root interfaces,
  model IDs, tool declarations and the complete existing reader dependency chain.
- Node samples are fragments, NOT standalone runnable workflows. Replace example
  bindings with existing approved bindings. Function/Struct samples use the
  accompanying metadata. Derived interface snapshots are not authored node fields.
- Per-type schemas add exact argument-key allowlists to the runtime JSON Schema.
  The JSON Schema is NOT the complete validator: `{}` does not mean arbitrary
  values are valid. Follow the exact semantic validation source in the appendix.
- Port examples show accepted connection types from the actual runtime checker.
  A permissive type list is not an implicit conversion or an output value type.
  Dynamic ports change with arguments/metadata; use the port-resolution source.
- Tool examples do not register tools or grant capabilities. `tool` in main can
  only preserve its existing workspace.get_file readers. No new tool calls.
- Source snapshots are design documentation, not instructions to execute Python.
  Generation validates samples; final candidate still requires runtime validation
  and compilation. Neither proves task performance.

## Example metadata / root interface context

```json
{
  "input_ports": [
    {
      "name": "value",
      "type": "content"
    }
  ],
  "output_ports": [
    {
      "name": "value",
      "type": "content"
    }
  ],
  "metadata": {
    "structs": [
      {
        "id": "Example",
        "name": "Example",
        "color": "#123456",
        "fields": [
          {
            "name": "text",
            "type": "content",
            "required": false
          }
        ]
      }
    ],
    "functions": [
      {
        "id": "example",
        "name": "Example function",
        "input_ports": [
          {
            "name": "value",
            "type": "content"
          }
        ],
        "output_ports": [
          {
            "name": "value",
            "type": "content"
          }
        ]
      }
    ]
  }
}
```

## Node declarations, schemas and concrete ports

### construct_content

```json
{
  "schema_ref": "#/$defs/node__construct_content",
  "arguments": [
    "append_items"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_construct_content",
        "type": "construct_content",
        "arguments": {
          "append_items": [
            {
              "type": "fixed",
              "value": "Example"
            }
          ]
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {},
        "output": {
          "content-out": [
            "content",
            "number",
            "list-content",
            "map-content",
            "struct:Example",
            "list-struct:Example"
          ]
        }
      }
    }
  ]
}
```

### construct_list

```json
{
  "schema_ref": "#/$defs/node__construct_list",
  "arguments": [
    "initial_value_count",
    "item_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_construct_list",
        "type": "construct_list",
        "arguments": {
          "item_type": "content",
          "initial_value_count": 1
        },
        "dataInputPorts": [
          "content-in-0"
        ]
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "content-in-0": [
            "content"
          ]
        },
        "output": {
          "list-out": [
            "list-content"
          ]
        }
      }
    }
  ]
}
```

### construct_map_content

```json
{
  "schema_ref": "#/$defs/node__construct_map_content",
  "arguments": [
    "mappings"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_construct_map_content",
        "type": "construct_map_content",
        "arguments": {
          "mappings": [
            {
              "key": "text",
              "value_source": "fixed",
              "value": "Example"
            }
          ]
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {},
        "output": {
          "map-out": [
            "map-content"
          ]
        }
      }
    }
  ]
}
```

### construct_message

```json
{
  "schema_ref": "#/$defs/node__construct_message",
  "arguments": [
    "role",
    "role_source"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_construct_message",
        "type": "construct_message",
        "arguments": {
          "role": "user",
          "role_source": "fixed"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "content-in": [
            "content"
          ],
          "reasoning-in": [
            "content"
          ],
          "tool-call-id-in": [
            "content"
          ],
          "tool-calls-in": [
            "list-content"
          ]
        },
        "output": {
          "content-out": [
            "content"
          ]
        }
      }
    },
    {
      "node": {
        "id": "example_construct_message",
        "type": "construct_message",
        "arguments": {
          "role": "user",
          "role_source": "port"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "content-in": [
            "content"
          ],
          "reasoning-in": [
            "content"
          ],
          "role-in": [
            "content"
          ],
          "tool-call-id-in": [
            "content"
          ],
          "tool-calls-in": [
            "list-content"
          ]
        },
        "output": {
          "content-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### construct_struct

```json
{
  "schema_ref": "#/$defs/node__construct_struct",
  "arguments": [
    "struct_id"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_construct_struct",
        "type": "construct_struct",
        "arguments": {
          "struct_id": "Example"
        },
        "dataInputPorts": [
          "text"
        ]
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "text": [
            "content"
          ]
        },
        "output": {
          "struct-out": [
            "struct:Example"
          ]
        }
      }
    }
  ]
}
```

### construct_tool

```json
{
  "schema_ref": "#/$defs/node__construct_tool",
  "arguments": [
    "description",
    "description_source",
    "required",
    "required_source",
    "schema",
    "schema_source",
    "tool_name",
    "tool_name_source"
  ],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_construct_tool",
        "type": "construct_tool",
        "arguments": {
          "tool_name": "example",
          "schema": {
            "type": "object",
            "properties": {}
          }
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {},
        "output": {
          "tool-out": [
            "content"
          ]
        }
      }
    },
    {
      "node": {
        "id": "example_construct_tool",
        "type": "construct_tool",
        "arguments": {
          "tool_name": "example",
          "schema": {
            "type": "object",
            "properties": {}
          },
          "tool_name_source": "port",
          "description_source": "port",
          "schema_source": "port",
          "required_source": "port"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "description-in": [
            "content"
          ],
          "name-in": [
            "content"
          ],
          "required-in": [
            "list-content"
          ],
          "schema-in": [
            "content"
          ]
        },
        "output": {
          "tool-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### context_create

```json
{
  "schema_ref": "#/$defs/node__context_create",
  "arguments": [
    "context_id",
    "value_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_context_create",
        "type": "context_create",
        "arguments": {
          "value_type": "content"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "initial-value": [
            "content"
          ]
        },
        "output": {
          "context-id": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### context_read

```json
{
  "schema_ref": "#/$defs/node__context_read",
  "arguments": [
    "context_id",
    "context_id_source",
    "value_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_context_read",
        "type": "context_read",
        "arguments": {
          "value_type": "content"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "context-id": [
            "content"
          ]
        },
        "output": {
          "value-out": [
            "content"
          ]
        }
      }
    },
    {
      "node": {
        "id": "example_context_read",
        "type": "context_read",
        "arguments": {
          "value_type": "content",
          "context_id_source": "fixed",
          "context_id": "example"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {},
        "output": {
          "value-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### context_write

```json
{
  "schema_ref": "#/$defs/node__context_write",
  "arguments": [
    "context_id",
    "context_id_source",
    "value_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_context_write",
        "type": "context_write",
        "arguments": {
          "value_type": "content"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "context-id": [
            "content"
          ],
          "value-in": [
            "content"
          ]
        },
        "output": {
          "context-id": [
            "content"
          ],
          "value-out": [
            "content"
          ]
        }
      }
    },
    {
      "node": {
        "id": "example_context_write",
        "type": "context_write",
        "arguments": {
          "value_type": "content",
          "context_id_source": "fixed",
          "context_id": "example"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "value-in": [
            "content"
          ]
        },
        "output": {
          "context-id": [
            "content"
          ],
          "value-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### deserialize_json

```json
{
  "schema_ref": "#/$defs/node__deserialize_json",
  "arguments": [
    "outputs"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_deserialize_json",
        "type": "deserialize_json",
        "arguments": {
          "outputs": [
            {
              "key": "text",
              "type": "content"
            }
          ]
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "content-in": [
            "content"
          ]
        },
        "output": {
          "text": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### foreach

```json
{
  "schema_ref": "#/$defs/node__foreach",
  "arguments": [
    "item_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_foreach",
        "type": "foreach",
        "arguments": {
          "item_type": "content"
        }
      },
      "control_in": [
        "control-in",
        "loop-in"
      ],
      "control_out": [
        "control-out",
        "loop-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "list-in": [
            "list-content"
          ]
        },
        "output": {
          "item-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### function_call

```json
{
  "schema_ref": "#/$defs/node__function_call",
  "arguments": [
    "function_id"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_function_call",
        "type": "function_call",
        "arguments": {
          "function_id": "example"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "function:value": [
            "content"
          ]
        },
        "output": {
          "function:value": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### function_input

```json
{
  "schema_ref": "#/$defs/node__function_input",
  "arguments": [],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_function_input",
        "type": "function_input",
        "arguments": {},
        "function_id": "example"
      },
      "control_in": [],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {},
        "output": {
          "function:value": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### function_output

```json
{
  "schema_ref": "#/$defs/node__function_output",
  "arguments": [],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_function_output",
        "type": "function_output",
        "arguments": {},
        "function_id": "example"
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [],
      "accepted_data_connection_types": {
        "input": {
          "function:value": [
            "content"
          ]
        },
        "output": {}
      }
    }
  ]
}
```

### input

```json
{
  "schema_ref": "#/$defs/node__input",
  "arguments": [],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_input",
        "type": "input",
        "arguments": {},
        "workflowPorts": [
          {
            "id": "workflow:value",
            "name": "value",
            "type": "content"
          }
        ]
      },
      "control_in": [],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {},
        "output": {
          "workflow:value": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### json_to_struct

```json
{
  "schema_ref": "#/$defs/node__json_to_struct",
  "arguments": [
    "value_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_json_to_struct",
        "type": "json_to_struct",
        "arguments": {
          "value_type": "struct:Example"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "content-in": [
            "content"
          ]
        },
        "output": {
          "value-out": [
            "struct:Example"
          ]
        }
      }
    }
  ]
}
```

### json_tool

```json
{
  "schema_ref": "#/$defs/node__json_tool",
  "arguments": [],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_json_tool",
        "type": "json_tool",
        "arguments": {}
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out",
        "error-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "arguments-json": [
            "content"
          ],
          "tool-name": [
            "content"
          ]
        },
        "output": {
          "error-json": [
            "content"
          ],
          "result-json": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### list_append

```json
{
  "schema_ref": "#/$defs/node__list_append",
  "arguments": [
    "item_type",
    "position"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_list_append",
        "type": "list_append",
        "arguments": {
          "item_type": "content",
          "position": "end"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "item-in": [
            "content"
          ],
          "list-in": [
            "list-content"
          ]
        },
        "output": {
          "list-out": [
            "list-content"
          ]
        }
      }
    }
  ]
}
```

### list_get

```json
{
  "schema_ref": "#/$defs/node__list_get",
  "arguments": [
    "index",
    "index_source",
    "value_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_list_get",
        "type": "list_get",
        "arguments": {
          "value_type": "list-content",
          "index_source": "fixed",
          "index": 0
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "list-in": [
            "list-content"
          ]
        },
        "output": {
          "item-out": [
            "content"
          ]
        }
      }
    },
    {
      "node": {
        "id": "example_list_get",
        "type": "list_get",
        "arguments": {
          "value_type": "list-content",
          "index_source": "port",
          "index": 0
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "index-in": [
            "number"
          ],
          "list-in": [
            "list-content"
          ]
        },
        "output": {
          "item-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### list_length

```json
{
  "schema_ref": "#/$defs/node__list_length",
  "arguments": [
    "value_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_list_length",
        "type": "list_length",
        "arguments": {
          "value_type": "list-content"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "list-in": [
            "list-content"
          ]
        },
        "output": {
          "length-out": [
            "number"
          ]
        }
      }
    }
  ]
}
```

### list_slice

```json
{
  "schema_ref": "#/$defs/node__list_slice",
  "arguments": [
    "start",
    "start_source",
    "step",
    "step_source",
    "stop",
    "stop_source",
    "value_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_list_slice",
        "type": "list_slice",
        "arguments": {
          "value_type": "list-content",
          "start_source": "fixed",
          "start": 0,
          "stop_source": "fixed",
          "stop": null,
          "step_source": "fixed",
          "step": 1
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "list-in": [
            "list-content"
          ]
        },
        "output": {
          "list-out": [
            "list-content"
          ]
        }
      }
    },
    {
      "node": {
        "id": "example_list_slice",
        "type": "list_slice",
        "arguments": {
          "value_type": "list-content",
          "start_source": "port",
          "start": 0,
          "stop_source": "port",
          "stop": null,
          "step_source": "port",
          "step": 1
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "list-in": [
            "list-content"
          ],
          "start-in": [
            "number"
          ],
          "step-in": [
            "number"
          ],
          "stop-in": [
            "number"
          ]
        },
        "output": {
          "list-out": [
            "list-content"
          ]
        }
      }
    }
  ]
}
```

### llm

```json
{
  "schema_ref": "#/$defs/node__llm",
  "arguments": [
    "model",
    "think",
    "tool_calls",
    "tools",
    "tools_source"
  ],
  "main_policy": "existing_model_no_tool_calls",
  "examples": [
    {
      "node": {
        "id": "example_llm",
        "type": "llm",
        "arguments": {
          "model": "EXISTING_MODEL_ID",
          "think": false,
          "tool_calls": false
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "messages-in": [
            "list-content"
          ]
        },
        "output": {
          "output": [
            "content",
            "number",
            "list-content",
            "map-content",
            "struct:Example",
            "list-struct:Example"
          ]
        }
      }
    },
    {
      "node": {
        "id": "example_llm",
        "type": "llm",
        "arguments": {
          "model": "EXISTING_MODEL_ID",
          "think": true,
          "tool_calls": true,
          "tools_source": "declared",
          "tools": []
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "available-tools-in": [
            "list-content"
          ],
          "messages-in": [
            "list-content"
          ]
        },
        "output": {
          "output": [
            "content",
            "number",
            "list-content",
            "map-content",
            "struct:Example",
            "list-struct:Example"
          ],
          "reasoning": [
            "content",
            "number",
            "list-content",
            "map-content",
            "struct:Example",
            "list-struct:Example"
          ],
          "tool_calls": [
            "list-content"
          ]
        }
      }
    },
    {
      "node": {
        "id": "example_llm",
        "type": "llm",
        "arguments": {
          "model": "EXISTING_MODEL_ID",
          "think": true,
          "tool_calls": true,
          "tools_source": "definitions"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "messages-in": [
            "list-content"
          ],
          "tools-in": [
            "list-content"
          ]
        },
        "output": {
          "output": [
            "content",
            "number",
            "list-content",
            "map-content",
            "struct:Example",
            "list-struct:Example"
          ],
          "reasoning": [
            "content",
            "number",
            "list-content",
            "map-content",
            "struct:Example",
            "list-struct:Example"
          ],
          "tool_calls": [
            "list-content"
          ]
        }
      }
    }
  ]
}
```

### local_tool

```json
{
  "schema_ref": "#/$defs/node__local_tool",
  "arguments": [
    "parameters",
    "tool"
  ],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_local_tool",
        "type": "local_tool",
        "arguments": {
          "tool": "example",
          "parameters": [
            "text"
          ]
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "text": [
            "content"
          ]
        },
        "output": {
          "output": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### map_content_get

```json
{
  "schema_ref": "#/$defs/node__map_content_get",
  "arguments": [],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_map_content_get",
        "type": "map_content_get",
        "arguments": {}
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "key-in": [
            "content"
          ],
          "map-in": [
            "map-content"
          ]
        },
        "output": {
          "content-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### number_to_content

```json
{
  "schema_ref": "#/$defs/node__number_to_content",
  "arguments": [],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_number_to_content",
        "type": "number_to_content",
        "arguments": {}
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "number-in": [
            "number"
          ]
        },
        "output": {
          "content-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### output

```json
{
  "schema_ref": "#/$defs/node__output",
  "arguments": [],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_output",
        "type": "output",
        "arguments": {},
        "workflowPorts": [
          {
            "id": "workflow:value",
            "name": "value",
            "type": "content"
          }
        ]
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [],
      "accepted_data_connection_types": {
        "input": {
          "workflow:value": [
            "content"
          ]
        },
        "output": {}
      }
    }
  ]
}
```

### output_to_terminal

```json
{
  "schema_ref": "#/$defs/node__output_to_terminal",
  "arguments": [],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_output_to_terminal",
        "type": "output_to_terminal",
        "arguments": {}
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "content-in": [
            "content"
          ]
        },
        "output": {}
      }
    }
  ]
}
```

### read_terminal_queue

```json
{
  "schema_ref": "#/$defs/node__read_terminal_queue",
  "arguments": [],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_read_terminal_queue",
        "type": "read_terminal_queue",
        "arguments": {}
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {},
        "output": {
          "list-out": [
            "list-content"
          ]
        }
      }
    }
  ]
}
```

### remote_async_tool

```json
{
  "schema_ref": "#/$defs/node__remote_async_tool",
  "arguments": [
    "callback",
    "parameters",
    "timeout_ms",
    "tool"
  ],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_remote_async_tool",
        "type": "remote_async_tool",
        "arguments": {
          "tool": "example",
          "parameters": [
            {
              "name": "text",
              "type": "content"
            }
          ]
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "text": [
            "content"
          ]
        },
        "output": {
          "task_id": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### remote_sync_tool

```json
{
  "schema_ref": "#/$defs/node__remote_sync_tool",
  "arguments": [
    "outputs",
    "parameters",
    "timeout_ms",
    "tool"
  ],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_remote_sync_tool",
        "type": "remote_sync_tool",
        "arguments": {
          "tool": "example",
          "parameters": [
            {
              "name": "text",
              "type": "content"
            }
          ],
          "outputs": [
            {
              "name": "result",
              "type": "content"
            }
          ]
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "text": [
            "content"
          ]
        },
        "output": {
          "result": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### router

```json
{
  "schema_ref": "#/$defs/node__router",
  "arguments": [
    "branches"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_router",
        "type": "router",
        "arguments": {
          "branches": [
            {
              "id": "yes",
              "name": "yes"
            }
          ]
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "branch$others",
        "yes"
      ],
      "accepted_data_connection_types": {
        "input": {
          "content-in": [
            "content",
            "number",
            "list-content",
            "map-content",
            "struct:Example",
            "list-struct:Example"
          ]
        },
        "output": {}
      }
    }
  ]
}
```

### session_create

```json
{
  "schema_ref": "#/$defs/node__session_create",
  "arguments": [
    "value_type"
  ],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_session_create",
        "type": "session_create",
        "arguments": {
          "value_type": "content"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "initial-value": [
            "content"
          ]
        },
        "output": {
          "session-id": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### session_read

```json
{
  "schema_ref": "#/$defs/node__session_read",
  "arguments": [
    "value_type"
  ],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_session_read",
        "type": "session_read",
        "arguments": {
          "value_type": "content"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "session-id": [
            "content"
          ]
        },
        "output": {
          "value-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### session_write

```json
{
  "schema_ref": "#/$defs/node__session_write",
  "arguments": [
    "value_type"
  ],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_session_write",
        "type": "session_write",
        "arguments": {
          "value_type": "content"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "session-id": [
            "content"
          ],
          "value-in": [
            "content"
          ]
        },
        "output": {
          "session-id": [
            "content"
          ],
          "value-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### spawn_and_wait_subprocess

```json
{
  "schema_ref": "#/$defs/node__spawn_and_wait_subprocess",
  "arguments": [],
  "main_policy": "forbidden",
  "examples": [
    {
      "node": {
        "id": "example_spawn_and_wait_subprocess",
        "type": "spawn_and_wait_subprocess",
        "arguments": {}
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out",
        "error-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "arguments-json": [
            "content"
          ],
          "workflow-file": [
            "content"
          ]
        },
        "output": {
          "error-json": [
            "content"
          ],
          "result-json": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### struct_get

```json
{
  "schema_ref": "#/$defs/node__struct_get",
  "arguments": [
    "field",
    "has_fallback",
    "missing",
    "struct_id"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_struct_get",
        "type": "struct_get",
        "arguments": {
          "struct_id": "Example",
          "field": "text",
          "missing": "error",
          "has_fallback": false
        },
        "dataInputPorts": [
          "struct-in"
        ]
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "struct-in": [
            "struct:Example"
          ]
        },
        "output": {
          "value-out": [
            "content"
          ]
        }
      }
    },
    {
      "node": {
        "id": "example_struct_get",
        "type": "struct_get",
        "arguments": {
          "struct_id": "Example",
          "field": "text",
          "missing": "fallback",
          "has_fallback": true
        },
        "dataInputPorts": [
          "struct-in",
          "fallback-in"
        ]
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "fallback-in": [
            "content"
          ],
          "struct-in": [
            "struct:Example"
          ]
        },
        "output": {
          "value-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### struct_to_json

```json
{
  "schema_ref": "#/$defs/node__struct_to_json",
  "arguments": [
    "value_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_struct_to_json",
        "type": "struct_to_json",
        "arguments": {
          "value_type": "struct:Example"
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "value-in": [
            "struct:Example"
          ]
        },
        "output": {
          "content-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### struct_update

```json
{
  "schema_ref": "#/$defs/node__struct_update",
  "arguments": [
    "remove_fields",
    "struct_id",
    "updates"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_struct_update",
        "type": "struct_update",
        "arguments": {
          "struct_id": "Example",
          "updates": [
            "text"
          ],
          "remove_fields": []
        },
        "dataInputPorts": [
          "struct-in",
          "text"
        ]
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "struct-in": [
            "struct:Example"
          ],
          "text": [
            "content"
          ]
        },
        "output": {
          "struct-out": [
            "struct:Example"
          ]
        }
      }
    }
  ]
}
```

### tool

```json
{
  "schema_ref": "#/$defs/node__tool",
  "arguments": [
    "callback",
    "mode",
    "outputs",
    "parameters",
    "timeout_ms",
    "tool"
  ],
  "main_policy": "preserve_existing_readers_only",
  "examples": [
    {
      "node": {
        "id": "example_tool",
        "type": "tool",
        "arguments": {
          "tool": "example",
          "parameters": [
            {
              "name": "text",
              "type": "content"
            }
          ],
          "outputs": [
            {
              "name": "result",
              "type": "content"
            }
          ]
        }
      },
      "control_in": [
        "control-in"
      ],
      "control_out": [
        "control-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "text": [
            "content"
          ]
        },
        "output": {
          "result": [
            "content"
          ]
        }
      }
    }
  ]
}
```

### while_pop

```json
{
  "schema_ref": "#/$defs/node__while_pop",
  "arguments": [
    "context_id",
    "context_id_source",
    "position",
    "value_type"
  ],
  "main_policy": "allowed_subject_to_validation",
  "examples": [
    {
      "node": {
        "id": "example_while_pop",
        "type": "while_pop",
        "arguments": {
          "value_type": "list-content",
          "position": "end",
          "context_id_source": "port"
        }
      },
      "control_in": [
        "control-in",
        "loop-in"
      ],
      "control_out": [
        "control-out",
        "loop-out"
      ],
      "accepted_data_connection_types": {
        "input": {
          "context-id": [
            "content"
          ]
        },
        "output": {
          "item-out": [
            "content"
          ]
        }
      }
    },
    {
      "node": {
        "id": "example_while_pop",
        "type": "while_pop",
        "arguments": {
          "value_type": "list-content",
          "position": "end",
          "context_id_source": "fixed",
          "context_id": "example"
        }
      },
      "control_in": [
        "control-in",
        "loop-in"
      ],
      "control_out": [
        "control-out",
        "loop-out"
      ],
      "accepted_data_connection_types": {
        "input": {},
        "output": {
          "item-out": [
            "content"
          ]
        }
      }
    }
  ]
}
```

## Complete runtime JSON Schema + per-type structural definitions

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://aagent.local/protocol/workflow/2.0/schema.json",
  "title": "AAgent Workflow 2.0",
  "type": "object",
  "required": [
    "schema_version",
    "input_ports",
    "output_ports",
    "nodes",
    "connections"
  ],
  "properties": {
    "schema_version": {
      "const": "2.0"
    },
    "description": {
      "type": "string"
    },
    "metadata": {
      "type": "object",
      "properties": {
        "max_execution_time_seconds": {
          "type": "integer",
          "description": "Maximum cumulative active execution time in seconds; negative values disable the limit."
        },
        "structs": {
          "type": "array",
          "items": {
            "type": "object",
            "required": [
              "id",
              "name",
              "color",
              "fields"
            ],
            "properties": {
              "id": {
                "type": "string",
                "description": "Struct type identifier. The editor saves the user-entered name as both id and name; legacy definitions with a separate name remain supported.",
                "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"
              },
              "name": {
                "type": "string",
                "description": "The editor saves the same value as id. Receivers preserve a different legacy display name and resolve type references using id.",
                "minLength": 1
              },
              "color": {
                "type": "string",
                "pattern": "^#[0-9A-Fa-f]{6}$"
              },
              "list_color": {
                "type": "string",
                "description": "Optional color for list-struct:<id>; defaults to color for older workflows.",
                "pattern": "^#[0-9A-Fa-f]{6}$"
              },
              "fields": {
                "type": "array",
                "items": {
                  "type": "object",
                  "required": [
                    "name",
                    "type",
                    "required"
                  ],
                  "properties": {
                    "name": {
                      "type": "string",
                      "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"
                    },
                    "type": {
                      "type": "string"
                    },
                    "required": {
                      "type": "boolean"
                    }
                  },
                  "additionalProperties": false
                }
              }
            },
            "additionalProperties": false
          }
        },
        "tools": {
          "type": "array",
          "maxItems": 100,
          "items": {
            "$ref": "#/$defs/toolDependency"
          }
        },
        "functions": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/function"
          }
        }
      },
      "additionalProperties": false
    },
    "input_ports": {
      "$ref": "#/$defs/ports"
    },
    "output_ports": {
      "$ref": "#/$defs/ports"
    },
    "remote_tools": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/toolContract"
      }
    },
    "nodes": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/node"
      }
    },
    "connections": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/connection"
      }
    }
  },
  "$defs": {
    "port": {
      "type": "object",
      "required": [
        "name",
        "type"
      ],
      "properties": {
        "name": {
          "type": "string",
          "minLength": 1
        },
        "type": {
          "type": "string",
          "pattern": "^(content|number|list-content|map-content|struct:[A-Za-z_][A-Za-z0-9_]*|list-struct:[A-Za-z_][A-Za-z0-9_]*)$"
        }
      },
      "additionalProperties": false
    },
    "ports": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/port"
      }
    },
    "toolContract": {
      "type": "object",
      "required": [
        "name",
        "input_ports",
        "output_ports"
      ],
      "properties": {
        "name": {
          "type": "string",
          "minLength": 1
        },
        "input_ports": {
          "$ref": "#/$defs/ports"
        },
        "output_ports": {
          "$ref": "#/$defs/ports"
        }
      },
      "additionalProperties": false
    },
    "mapMapping": {
      "oneOf": [
        {
          "type": "object",
          "required": [
            "key",
            "value"
          ],
          "properties": {
            "key": {
              "type": "string",
              "minLength": 1
            },
            "value_source": {
              "const": "fixed"
            },
            "value": {
              "type": "string"
            }
          },
          "additionalProperties": false
        },
        {
          "type": "object",
          "required": [
            "key",
            "value_source",
            "port_id"
          ],
          "properties": {
            "key": {
              "type": "string",
              "minLength": 1
            },
            "value_source": {
              "const": "port"
            },
            "port_id": {
              "type": "string",
              "minLength": 1,
              "not": {
                "enum": [
                  "control-in",
                  "control-out"
                ]
              }
            }
          },
          "additionalProperties": false
        }
      ]
    },
    "node": {
      "type": "object",
      "required": [
        "id",
        "type"
      ],
      "properties": {
        "id": {
          "type": "string",
          "minLength": 1
        },
        "type": {
          "enum": [
            "input",
            "output",
            "router",
            "construct_message",
            "construct_content",
            "construct_map_content",
            "map_content_get",
            "number_to_content",
            "output_to_terminal",
            "read_terminal_queue",
            "deserialize_json",
            "construct_list",
            "list_append",
            "list_length",
            "list_get",
            "list_slice",
            "foreach",
            "while_pop",
            "llm",
            "local_tool",
            "remote_sync_tool",
            "remote_async_tool",
            "json_tool",
            "context_create",
            "context_read",
            "context_write",
            "session_create",
            "session_read",
            "session_write",
            "spawn_and_wait_subprocess",
            "construct_struct",
            "struct_get",
            "struct_update",
            "struct_to_json",
            "json_to_struct",
            "tool",
            "function_input",
            "function_output",
            "function_call",
            "construct_tool"
          ]
        },
        "name": {
          "type": "string"
        },
        "x": {
          "type": "number"
        },
        "y": {
          "type": "number"
        },
        "arguments": {
          "type": "object",
          "properties": {
            "branches": {
              "type": "array",
              "items": {
                "type": "object",
                "required": [
                  "id",
                  "name"
                ],
                "properties": {
                  "id": {
                    "type": "string",
                    "minLength": 1,
                    "not": {
                      "const": "branch$others"
                    }
                  },
                  "name": {
                    "type": "string",
                    "minLength": 1
                  }
                },
                "additionalProperties": false
              }
            },
            "function_id": {
              "type": "string",
              "minLength": 1,
              "description": "The target function of a function_call node."
            }
          }
        },
        "workflowPorts": {
          "type": "array",
          "items": {
            "type": "object",
            "required": [
              "id",
              "name",
              "type"
            ],
            "properties": {
              "id": {
                "type": "string",
                "minLength": 1
              },
              "name": {
                "type": "string",
                "minLength": 1
              },
              "type": {
                "$ref": "#/$defs/port/properties/type"
              }
            },
            "additionalProperties": false
          }
        },
        "dataInputPorts": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "input_ports": {
          "$ref": "#/$defs/ports"
        },
        "output_ports": {
          "$ref": "#/$defs/ports"
        },
        "function_id": {
          "type": "string",
          "minLength": 1,
          "description": "Identifies the function for function_input/function_output. Ordinary node membership is inferred from control flow during validation; legacy body labels are ignored."
        }
      },
      "additionalProperties": false,
      "allOf": [
        {
          "if": {
            "properties": {
              "type": {
                "const": "router"
              }
            },
            "required": [
              "type"
            ]
          },
          "then": {
            "required": [
              "arguments"
            ],
            "properties": {
              "arguments": {
                "required": [
                  "branches"
                ],
                "additionalProperties": false,
                "properties": {
                  "branches": {
                    "$ref": "#/$defs/node/properties/arguments/properties/branches"
                  }
                }
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "const": "construct_map_content"
              }
            },
            "required": [
              "type"
            ]
          },
          "then": {
            "required": [
              "arguments"
            ],
            "properties": {
              "arguments": {
                "type": "object",
                "required": [
                  "mappings"
                ],
                "properties": {
                  "mappings": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                      "$ref": "#/$defs/mapMapping"
                    }
                  }
                },
                "additionalProperties": false
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "enum": [
                  "context_create",
                  "context_read",
                  "context_write",
                  "struct_to_json",
                  "json_to_struct"
                ]
              }
            },
            "required": [
              "type"
            ]
          },
          "then": {
            "properties": {
              "arguments": {
                "type": "object",
                "properties": {
                  "value_type": {
                    "anyOf": [
                      {
                        "enum": [
                          "content",
                          "number",
                          "map-content",
                          "list-content"
                        ]
                      },
                      {
                        "type": "string",
                        "pattern": "^(struct|list-struct):[A-Za-z_][A-Za-z0-9_]*$"
                      }
                    ]
                  },
                  "context_id_source": {
                    "enum": [
                      "port",
                      "fixed"
                    ]
                  },
                  "context_id": {
                    "type": "string",
                    "minLength": 1
                  }
                },
                "additionalProperties": false
              }
            }
          },
          "else": {
            "if": {
              "properties": {
                "type": {
                  "not": {
                    "enum": [
                      "while_pop",
                      "list_length",
                      "list_get",
                      "list_slice"
                    ]
                  }
                }
              }
            },
            "then": {
              "properties": {
                "arguments": {
                  "type": "object",
                  "properties": {
                    "value_type": {
                      "enum": [
                        "content",
                        "number",
                        "map-content",
                        "list-content"
                      ]
                    }
                  }
                }
              }
            }
          }
        },
        {
          "not": {
            "properties": {
              "type": {
                "not": {
                  "enum": [
                    "context_read",
                    "context_write",
                    "while_pop"
                  ]
                }
              },
              "arguments": {
                "required": [
                  "context_id_source"
                ]
              }
            },
            "required": [
              "type",
              "arguments"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "const": "tool"
              }
            },
            "required": [
              "type"
            ]
          },
          "then": {
            "required": [
              "arguments"
            ],
            "properties": {
              "arguments": {
                "type": "object",
                "required": [
                  "tool",
                  "parameters",
                  "outputs"
                ],
                "properties": {
                  "tool": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 128
                  },
                  "parameters": {
                    "$ref": "#/$defs/toolPorts"
                  },
                  "outputs": {
                    "$ref": "#/$defs/toolPorts"
                  },
                  "mode": {
                    "const": "sync"
                  },
                  "timeout_ms": {
                    "type": "integer",
                    "minimum": 1
                  },
                  "callback": {
                    "type": "null"
                  }
                },
                "additionalProperties": false
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "const": "while_pop"
              }
            },
            "required": [
              "type"
            ]
          },
          "then": {
            "required": [
              "arguments"
            ],
            "properties": {
              "arguments": {
                "type": "object",
                "required": [
                  "value_type"
                ],
                "properties": {
                  "value_type": {
                    "anyOf": [
                      {
                        "enum": [
                          "list-content"
                        ]
                      },
                      {
                        "type": "string",
                        "pattern": "^list-struct:[A-Za-z_][A-Za-z0-9_]*$"
                      }
                    ]
                  },
                  "position": {
                    "enum": [
                      "start",
                      "end"
                    ],
                    "default": "end"
                  },
                  "context_id_source": {
                    "enum": [
                      "port",
                      "fixed"
                    ],
                    "default": "port"
                  },
                  "context_id": {
                    "type": "string",
                    "minLength": 1
                  }
                },
                "additionalProperties": false,
                "allOf": [
                  {
                    "if": {
                      "properties": {
                        "context_id_source": {
                          "const": "fixed"
                        }
                      },
                      "required": [
                        "context_id_source"
                      ]
                    },
                    "then": {
                      "required": [
                        "context_id"
                      ]
                    }
                  }
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "const": "list_length"
              }
            },
            "required": [
              "type"
            ]
          },
          "then": {
            "required": [
              "arguments"
            ],
            "properties": {
              "arguments": {
                "type": "object",
                "required": [
                  "value_type"
                ],
                "properties": {
                  "value_type": {
                    "anyOf": [
                      {
                        "enum": [
                          "list-content"
                        ]
                      },
                      {
                        "type": "string",
                        "pattern": "^list-struct:[A-Za-z_][A-Za-z0-9_]*$"
                      }
                    ]
                  }
                },
                "additionalProperties": false
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "const": "list_slice"
              }
            },
            "required": [
              "type"
            ]
          },
          "then": {
            "required": [
              "arguments"
            ],
            "properties": {
              "arguments": {
                "type": "object",
                "required": [
                  "value_type"
                ],
                "properties": {
                  "value_type": {
                    "anyOf": [
                      {
                        "enum": [
                          "list-content"
                        ]
                      },
                      {
                        "type": "string",
                        "pattern": "^list-struct:[A-Za-z_][A-Za-z0-9_]*$"
                      }
                    ]
                  },
                  "start_source": {
                    "enum": [
                      "port",
                      "fixed"
                    ]
                  },
                  "start": {
                    "type": [
                      "integer",
                      "null"
                    ]
                  },
                  "stop_source": {
                    "enum": [
                      "port",
                      "fixed"
                    ]
                  },
                  "stop": {
                    "type": [
                      "integer",
                      "null"
                    ]
                  },
                  "step_source": {
                    "enum": [
                      "port",
                      "fixed"
                    ]
                  },
                  "step": {
                    "type": [
                      "integer",
                      "null"
                    ],
                    "not": {
                      "const": 0
                    }
                  }
                },
                "additionalProperties": false
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "const": "list_get"
              }
            },
            "required": [
              "type"
            ]
          },
          "then": {
            "required": [
              "arguments"
            ],
            "properties": {
              "arguments": {
                "type": "object",
                "required": [
                  "value_type"
                ],
                "properties": {
                  "value_type": {
                    "anyOf": [
                      {
                        "enum": [
                          "list-content"
                        ]
                      },
                      {
                        "type": "string",
                        "pattern": "^list-struct:[A-Za-z_][A-Za-z0-9_]*$"
                      }
                    ]
                  },
                  "index_source": {
                    "enum": [
                      "port",
                      "fixed"
                    ]
                  },
                  "index": {
                    "type": "integer"
                  }
                },
                "additionalProperties": false,
                "allOf": [
                  {
                    "if": {
                      "properties": {
                        "index_source": {
                          "const": "fixed"
                        }
                      },
                      "required": [
                        "index_source"
                      ]
                    },
                    "then": {
                      "required": [
                        "index"
                      ]
                    }
                  }
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "enum": [
                  "function_input",
                  "function_output"
                ]
              }
            },
            "required": [
              "type"
            ]
          },
          "then": {
            "required": [
              "function_id"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "const": "function_call"
              }
            },
            "required": [
              "type"
            ]
          },
          "then": {
            "required": [
              "arguments"
            ],
            "properties": {
              "arguments": {
                "required": [
                  "function_id"
                ]
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "const": "construct_tool"
              }
            }
          },
          "then": {
            "properties": {
              "arguments": {
                "type": "object",
                "properties": {
                  "tool_name_source": {
                    "enum": [
                      "fixed",
                      "port"
                    ]
                  },
                  "description_source": {
                    "enum": [
                      "fixed",
                      "port"
                    ]
                  },
                  "schema_source": {
                    "enum": [
                      "fixed",
                      "port"
                    ]
                  },
                  "required_source": {
                    "enum": [
                      "fixed",
                      "port"
                    ]
                  },
                  "tool_name": {
                    "type": "string"
                  },
                  "description": {
                    "type": "string"
                  },
                  "schema": {
                    "type": [
                      "object",
                      "string"
                    ]
                  },
                  "required": {
                    "type": "array",
                    "items": {
                      "type": "string",
                      "minLength": 1
                    },
                    "uniqueItems": true
                  }
                },
                "additionalProperties": false
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "type": {
                "const": "llm"
              }
            }
          },
          "then": {
            "properties": {
              "arguments": {
                "properties": {
                  "tools_source": {
                    "enum": [
                      "declared",
                      "definitions"
                    ]
                  }
                }
              }
            }
          }
        }
      ]
    },
    "connection": {
      "type": "object",
      "required": [
        "fromId",
        "fromPortId",
        "toId",
        "toPortId",
        "type"
      ],
      "properties": {
        "id": {
          "type": "string"
        },
        "fromId": {
          "type": "string",
          "minLength": 1
        },
        "fromPortId": {
          "type": "string",
          "minLength": 1
        },
        "toId": {
          "type": "string",
          "minLength": 1
        },
        "toPortId": {
          "type": "string",
          "minLength": 1
        },
        "type": {
          "anyOf": [
            {
              "enum": [
                "control",
                "content",
                "number",
                "list-content",
                "map-content"
              ]
            },
            {
              "type": "string",
              "pattern": "^(struct|list-struct):[A-Za-z_][A-Za-z0-9_]*$"
            }
          ]
        }
      },
      "additionalProperties": false
    },
    "toolDependency": {
      "type": "object",
      "required": [
        "name",
        "kind",
        "input_ports",
        "output_ports"
      ],
      "properties": {
        "name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 128
        },
        "kind": {
          "enum": [
            "local",
            "remote"
          ]
        },
        "input_ports": {
          "$ref": "#/$defs/toolPorts"
        },
        "output_ports": {
          "$ref": "#/$defs/toolPorts"
        }
      },
      "additionalProperties": false
    },
    "toolPorts": {
      "type": "array",
      "maxItems": 50,
      "items": {
        "type": "object",
        "required": [
          "name",
          "type"
        ],
        "properties": {
          "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 80,
            "not": {
              "enum": [
                "control-in",
                "control-out"
              ]
            }
          },
          "type": {
            "enum": [
              "content",
              "number",
              "map-content",
              "list-content"
            ]
          }
        },
        "additionalProperties": false
      }
    },
    "function": {
      "type": "object",
      "required": [
        "id",
        "name",
        "input_ports",
        "output_ports"
      ],
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"
        },
        "name": {
          "type": "string",
          "minLength": 1
        },
        "input_ports": {
          "$ref": "#/$defs/ports"
        },
        "output_ports": {
          "$ref": "#/$defs/ports"
        }
      },
      "additionalProperties": false
    },
    "node__construct_content": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "construct_content"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "append_items": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__construct_list": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "construct_list"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "initial_value_count": {},
                "item_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__construct_map_content": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "construct_map_content"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "mappings": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__construct_message": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "construct_message"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "role": {},
                "role_source": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__construct_struct": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "construct_struct"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "struct_id": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__construct_tool": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "construct_tool"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "description": {},
                "description_source": {},
                "required": {},
                "required_source": {},
                "schema": {},
                "schema_source": {},
                "tool_name": {},
                "tool_name_source": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__context_create": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "context_create"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "context_id": {},
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__context_read": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "context_read"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "context_id": {},
                "context_id_source": {},
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__context_write": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "context_write"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "context_id": {},
                "context_id_source": {},
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__deserialize_json": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "deserialize_json"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "outputs": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__foreach": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "foreach"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "item_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__function_call": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "function_call"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "function_id": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__function_input": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "function_input"
            },
            "arguments": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__function_output": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "function_output"
            },
            "arguments": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__input": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "input"
            },
            "arguments": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__json_to_struct": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "json_to_struct"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__json_tool": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "json_tool"
            },
            "arguments": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__list_append": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "list_append"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "item_type": {},
                "position": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__list_get": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "list_get"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "index": {},
                "index_source": {},
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__list_length": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "list_length"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__list_slice": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "list_slice"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "start": {},
                "start_source": {},
                "step": {},
                "step_source": {},
                "stop": {},
                "stop_source": {},
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__llm": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "llm"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "model": {},
                "think": {},
                "tool_calls": {},
                "tools": {},
                "tools_source": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__local_tool": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "local_tool"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "parameters": {},
                "tool": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__map_content_get": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "map_content_get"
            },
            "arguments": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__number_to_content": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "number_to_content"
            },
            "arguments": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__output": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "output"
            },
            "arguments": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__output_to_terminal": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "output_to_terminal"
            },
            "arguments": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__read_terminal_queue": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "read_terminal_queue"
            },
            "arguments": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__remote_async_tool": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "remote_async_tool"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "callback": {},
                "parameters": {},
                "timeout_ms": {},
                "tool": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__remote_sync_tool": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "remote_sync_tool"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "outputs": {},
                "parameters": {},
                "timeout_ms": {},
                "tool": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__router": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "router"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "branches": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__session_create": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "session_create"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__session_read": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "session_read"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__session_write": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "session_write"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__spawn_and_wait_subprocess": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "spawn_and_wait_subprocess"
            },
            "arguments": {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__struct_get": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "struct_get"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "field": {},
                "has_fallback": {},
                "missing": {},
                "struct_id": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__struct_to_json": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "struct_to_json"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__struct_update": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "struct_update"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "remove_fields": {},
                "struct_id": {},
                "updates": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__tool": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "tool"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "callback": {},
                "mode": {},
                "outputs": {},
                "parameters": {},
                "timeout_ms": {},
                "tool": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    },
    "node__while_pop": {
      "allOf": [
        {
          "$ref": "#/$defs/node"
        },
        {
          "properties": {
            "type": {
              "const": "while_pop"
            },
            "arguments": {
              "type": "object",
              "properties": {
                "context_id": {},
                "context_id_source": {},
                "position": {},
                "value_type": {}
              },
              "additionalProperties": false
            }
          }
        }
      ]
    }
  }
}
```

## Exact runtime semantic validation and port rules (source excerpts)

### agent/workflow_contract.py

```python
def data_ports_for_node(
    node: dict[str, Any],
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    node_type = node["type"]
    declared_inputs = set(node.get("dataInputPorts", []))
    if node_type == "input":
        return declared_inputs, {
            port["id"] for port in boundary_ports(input_ports)
        }
    if node_type == "output":
        return declared_inputs | {
            port["id"] for port in boundary_ports(output_ports)
        }, set()
    if node_type == "function_input":
        return declared_inputs, {f"function:{port['name']}" for port in node.get("function_ports", [])}
    if node_type == "function_output":
        return declared_inputs | {f"function:{port['name']}" for port in node.get("function_ports", [])}, set()
    if node_type == "function_call":
        return (
            {f"function:{port['name']}" for port in node.get("input_ports", [])},
            {f"function:{port['name']}" for port in node.get("output_ports", [])},
        )
    if node_type == "router":
        return declared_inputs | {"content-in"}, set()
    if node_type == "llm":
        outputs = {"output"}
        if node_argument(node, "think") is True:
            outputs.add("reasoning")
        if node_argument(node, "tool_calls") is True:
            outputs.add("tool_calls")
        inputs = {"messages-in"}
        if node_argument(node, "tool_calls") is True:
            inputs.add("tools-in" if node_argument(node, "tools_source", "declared") == "definitions" else "available-tools-in")
        return inputs, outputs
    if node_type == "construct_tool":
        from workflow_tools import TOOL_FIELDS, TOOL_PORTS
        return {TOOL_PORTS[field] for field in TOOL_FIELDS if node_argument(node, f"{field}_source", "fixed") == "port"}, {"tool-out"}
    if node_type == "construct_message":
        inputs = declared_inputs | {"content-in", "reasoning-in", "tool-calls-in", "tool-call-id-in"}
        if node_argument(node, "role_source", "fixed") == "port":
            inputs.add("role-in")
        return inputs, {"content-out"}
    if node_type == "construct_content":
        return declared_inputs, {"content-out"}
    if node_type == "construct_map_content":
        return declared_inputs, {"map-out"}
    if node_type == "construct_struct":
        return declared_inputs, {"struct-out"}
    if node_type == "struct_get":
        inputs = declared_inputs | {"struct-in"}
        if node_argument(node, "has_fallback"):
            inputs.add("fallback-in")
        return inputs, {"value-out"}
    if node_type == "struct_update":
        return declared_inputs | {"struct-in"}, {"struct-out"}
    if node_type in {"struct_to_json", "json_to_struct"}:
        return declared_inputs | ({"value-in"} if node_type == "struct_to_json" else {"content-in"}), {"content-out" if node_type == "struct_to_json" else "value-out"}
    if node_type == "number_to_content":
        return {"number-in"}, {"content-out"}
    if node_type == "map_content_get":
        return declared_inputs | {"map-in", "key-in"}, {"content-out"}
    if node_type == "read_terminal_queue":
        return set(), {"list-out"}
    if node_type == "output_to_terminal":
        return declared_inputs | {"content-in"}, set()
    if node_type == "deserialize_json":
        return {"content-in"}, {
            output["key"] for output in node_argument(node, "outputs", [])
        }
    if node_type == "construct_list":
        return declared_inputs, {"list-out"}
    if node_type == "list_get":
        inputs = {"list-in"} if node_argument(node, "index_source", "port") == "fixed" else {"list-in", "index-in"}
        return inputs, {"item-out"}
    if node_type == "list_length":
        return {"list-in"}, {"length-out"}
    if node_type == "list_slice":
        return {"list-in"} | {
            f"{name}-in" for name in ("start", "stop", "step")
            if node_argument(node, f"{name}_source", "port") != "fixed"
        }, {"list-out"}
    if node_type == "list_append":
        return declared_inputs | {"list-in", "item-in"}, {"list-out"}
    if node_type == "foreach":
        return declared_inputs | {"list-in"}, {"item-out"}
    if node_type == "while_pop":
        id_inputs = {"context-id"} if node_argument(node, "context_id_source", "port") == "port" else set()
        return id_inputs, {"item-out"}
    if node_type == "tool":
        outputs = {output["name"] for output in node_argument(node, "outputs", [])}
        return declared_inputs | set(tool_parameter_names(node)), outputs
    if node_type == "json_tool":
        return declared_inputs | {"tool-name", "arguments-json"}, {"result-json", "error-json"}
    if node_type == "local_tool":
        return declared_inputs | set(tool_parameter_names(node)), {"output"}
    if node_type == "remote_sync_tool":
        return declared_inputs | set(tool_parameter_names(node)), {
            output["name"] for output in node_argument(node, "outputs", [])
        }
    if node_type == "remote_async_tool":
        return declared_inputs | set(tool_parameter_names(node)), {"task_id"}
    if node_type in {"context_create", "session_create"}:
        return {"initial-value"}, {"context-id" if node_type == "context_create" else "session-id"}
    if node_type in {"context_read", "session_read"}:
        input_ports = {"context-id"} if node_type == "context_read" and node_argument(node, "context_id_source", "port") == "port" else ({"session-id"} if node_type == "session_read" else set())
        return input_ports, {"value-out"}
    if node_type in {"context_write", "session_write"}:
        id_port = "context-id" if node_type == "context_write" else "session-id"
        id_inputs = {id_port} if node_type == "session_write" or node_argument(node, "context_id_source", "port") == "port" else set()
        return id_inputs | {"value-in"}, {id_port, "value-out"}
    if node_type == "spawn_and_wait_subprocess":
        return {"workflow-file", "arguments-json"}, {"result-json", "error-json"}
    return declared_inputs, set()

def data_type_for_port(
    node: dict[str, Any], port_id: str, struct_definitions: dict[str, Any] | None = None
) -> str | None:
    definitions = struct_definitions or {}
    kind = node.get("type")
    if kind in {"function_input", "function_output"}:
        return next((port["type"] for port in node.get("function_ports", []) if f"function:{port['name']}" == port_id), None)
    value_type = node_argument(node, "value_type")
    if kind == "construct_message":
        return "list-content" if port_id == "tool-calls-in" else "content"
    if kind == "construct_tool":
        return "list-content" if port_id == "required-in" else "content"
    if kind == "construct_struct":
        sid = node_argument(node, "struct_id")
        if port_id == "struct-out": return f"struct:{sid}"
        return next((f["type"] for f in definitions.get(sid, {}).get("fields", []) if f["name"] == port_id), None)
    if kind == "struct_get":
        sid = node_argument(node, "struct_id")
        field_type = next((f["type"] for f in definitions.get(sid, {}).get("fields", []) if f["name"] == node_argument(node, "field")), None)
        if port_id == "struct-in": return f"struct:{sid}"
        if port_id in {"fallback-in", "value-out"}: return field_type
    if kind == "struct_update":
        sid = node_argument(node, "struct_id")
        if port_id in {"struct-in", "struct-out"}: return f"struct:{sid}"
        return next((f["type"] for f in definitions.get(sid, {}).get("fields", []) if f["name"] == port_id), None)
    if kind == "struct_to_json":
        return value_type if port_id == "value-in" else ("content" if port_id == "content-out" else None)
    if kind == "json_to_struct":
        return "content" if port_id == "content-in" else (value_type if port_id == "value-out" else None)
    if kind == "number_to_content":
        return {"number-in": "number", "content-out": "content"}.get(port_id)
    if kind == "read_terminal_queue":
        return "list-content" if port_id == "list-out" else None
    if kind == "construct_list":
        return f"list-{node_argument(node, 'item_type')}" if port_id == "list-out" else node_argument(node, "item_type")
    if kind == "list_get":
        if port_id == "list-in": return value_type
        if port_id == "index-in": return "number" if node_argument(node, "index_source", "port") != "fixed" else None
        if port_id == "item-out": return value_type.removeprefix("list-")
        return None
    if kind == "list_length":
        return value_type if port_id == "list-in" else ("number" if port_id == "length-out" else None)
    if kind == "list_slice":
        if port_id in {"list-in", "list-out"}: return value_type
        for name in ("start", "stop", "step"):
            if port_id == f"{name}-in" and node_argument(node, f"{name}_source", "port") != "fixed":
                return "number"
        return None
    if kind == "list_append":
        if port_id in {"list-in", "list-out"}: return f"list-{node_argument(node, 'item_type')}"
        return node_argument(node, "item_type") if port_id == "item-in" else None
    if kind == "foreach":
        return f"list-{node_argument(node, 'item_type')}" if port_id == "list-in" else (node_argument(node, "item_type") if port_id == "item-out" else None)
    if kind == "while_pop":
        if port_id == "context-id": return "content"
        if port_id == "item-out": return value_type.removeprefix("list-")
    if kind in {"context_create", "context_read", "context_write"}:
        if port_id in {"initial-value", "value-in", "value-out"}: return value_type
        if port_id == "context-id": return "content"
    return None

def control_ports_for_node(node: dict[str, Any]) -> tuple[set[str], set[str]]:
    node_type = node["type"]
    if node_type in {"input", "function_input"}:
        return set(), {"control-out"}
    if node_type in {"output", "function_output"}:
        return {"control-in"}, set()
    if node_type == "router":
        return {"control-in"}, {
            branch["id"] for branch in node_argument(node, "branches", [])
        } | {"branch$others"}
    if node_type in {"json_tool", "spawn_and_wait_subprocess"}:
        return {"control-in"}, {"control-out", "error-out"}
    if node_type in {"foreach", "while_pop"}:
        return {"control-in", "loop-in"}, {"control-out", "loop-out"}
    return {"control-in"}, {"control-out"}

def connection_validation_error(
    connection: Any,
    nodes_by_id: dict[str, dict[str, Any]],
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
    struct_definitions: dict[str, Any] | None = None,
) -> str | None:
    if not isinstance(connection, dict):
        return "connection must be an object"
    from_id = connection.get("fromId")
    to_id = connection.get("toId")
    from_port = connection.get("fromPortId")
    to_port = connection.get("toPortId")
    connection_type = connection.get("type")
    if not all(isinstance(value, str) and value for value in (from_id, to_id, from_port, to_port)):
        return "connection endpoints must be non-empty strings"
    source_node = nodes_by_id.get(from_id)
    target_node = nodes_by_id.get(to_id)
    if source_node is None or target_node is None:
        return "connection references an unknown node"
    try:
        if connection_type == "control":
            source_inputs, source_outputs = control_ports_for_node(source_node)
            target_inputs, target_outputs = control_ports_for_node(target_node)
            if from_port not in source_outputs:
                return f"invalid control output: {from_port}"
            if to_port not in target_inputs:
                return f"invalid control input: {to_port}"
            return None
        if connection_type not in DATA_CONNECTION_TYPES and not connection_type.startswith(("struct:", "list-struct:")):
            return "connection type is unsupported"
        _, source_outputs = data_ports_for_node(source_node, input_ports, output_ports)
        target_inputs, _ = data_ports_for_node(target_node, input_ports, output_ports)
        if from_port not in source_outputs or to_port not in target_inputs:
            return "unknown data port"
        source_expected = data_type_for_port(source_node, from_port, struct_definitions)
        target_expected = data_type_for_port(target_node, to_port, struct_definitions)
        if source_node["type"] == "function_call":
            source_expected = next(p["type"] for p in source_node["output_ports"] if f"function:{p['name']}" == from_port)
        if target_node["type"] == "function_call":
            target_expected = next(p["type"] for p in target_node["input_ports"] if f"function:{p['name']}" == to_port)
        if source_expected is not None and connection_type != source_expected:
            return f"source port {from_port} requires {source_expected} data"
        if target_expected is not None and connection_type != target_expected:
            return f"target port {to_port} requires {target_expected} data"
        if connection_type.startswith(("struct:", "list-struct:")):
            ref = connection_type.split(":", 1)[1]
            if struct_definitions is None or ref not in struct_definitions:
                return "Struct type is not declared in this Workflow"
        if source_node["type"] == "input":
            source_port = next(port for port in boundary_ports(input_ports) if port["id"] == from_port)
            if connection_type != source_port["type"]:
                return f"workflow input port {from_port} requires {source_port['type']} data"
        if target_node["type"] == "output":
            target_port = next(port for port in boundary_ports(output_ports) if port["id"] == to_port)
            if connection_type != target_port["type"]:
                return f"workflow output port {to_port} requires {target_port['type']} data"
        if (source_node["type"] == "spawn_and_wait_subprocess" or target_node["type"] == "spawn_and_wait_subprocess") and connection_type != "content":
            return "subprocess JSON ports require content data"
        if target_node["type"] in {"tool", "local_tool", "remote_sync_tool", "remote_async_tool", "json_tool"} and connection_type != tool_parameter_type(target_node, to_port):
            return f"tool input {to_port} requires {tool_parameter_type(target_node, to_port)} data"
        if source_node["type"] in {"tool", "local_tool", "remote_sync_tool", "remote_async_tool", "json_tool"} and connection_type != tool_output_type(source_node, from_port):
            return f"tool output {from_port} requires {tool_output_type(source_node, from_port)} data"
        if target_node["type"] in {"context_create", "context_write", "session_create", "session_write"}:
            value_port = "initial-value" if target_node["type"].endswith("create") else "value-in"
            expected_type = node_argument(target_node, "value_type") if to_port == value_port else "content"
            if connection_type != expected_type:
                return f"context/session input {to_port} requires {expected_type} data"
        if target_node["type"] in {"context_read", "session_read"} and connection_type != "content":
            return f"{target_node['type']} output requires content data"
        if source_node["type"] in {"context_create", "session_create"} and connection_type != "content":
            return f"{source_node['type']} output requires content data"
        if source_node["type"] in {"context_read", "context_write", "session_read", "session_write"}:
            expected_type = "content" if from_port in {"context-id", "session-id"} else node_argument(source_node, "value_type")
            if connection_type != expected_type:
                return f"context/session output {from_port} requires {expected_type} data"
        if target_node["type"] == "output_to_terminal" and connection_type != "content":
            return "output_to_terminal content-in requires content data"
        if target_node["type"] == "deserialize_json" and (
            to_port != "content-in" or connection_type != "content"
        ):
            return "deserialize_json content-in requires content data"
        if target_node["type"] == "map_content_get":
            expected_type = "map-content" if to_port == "map-in" else "content"
            if to_port not in {"map-in", "key-in"} or connection_type != expected_type:
                return f"map_content_get {to_port} requires {expected_type} data"
        if target_node["type"] == "construct_map_content" and connection_type != "content":
            return "construct_map_content value input requires content data"
        if source_node["type"] == "construct_map_content" and (
            from_port != "map-out" or connection_type != "map-content"
        ):
            return "construct_map_content map-out requires map-content data"
        if source_node["type"] == "map_content_get" and (
            from_port != "content-out" or connection_type != "content"
        ):
            return "map_content_get content-out requires content data"
        if source_node["type"] == "deserialize_json":
            output_type = next(
                (
                    output["type"]
                    for output in node_argument(source_node, "outputs", [])
                    if output["key"] == from_port
                ),
                None,
            )
            if connection_type != output_type:
                return f"deserialize_json output {from_port} requires {output_type} data"
        source_type = source_node["type"]
        target_type = target_node["type"]
        if target_type == "llm":
            expected_type = "list-content"
            if connection_type != expected_type:
                return f"llm {to_port} input requires {expected_type} data"
        if target_type == "construct_tool":
            expected_type = "list-content" if to_port == "required-in" else "content"
            if connection_type != expected_type:
                return f"construct_tool {to_port} requires {expected_type} data"
        if source_type == "construct_tool" and connection_type != "content":
            return "construct_tool tool-out requires content data"
        if target_type == "construct_message":
            expected_type = "list-content" if to_port == "tool-calls-in" else "content"
            if connection_type != expected_type:
                return f"construct_message {to_port} requires {expected_type} data"
        if source_type == "construct_message" and connection_type != "content":
            return "construct_message content-out requires content data"
        if target_type == "construct_list" and connection_type != node_argument(target_node, "item_type"):
            return f"construct_list input requires {node_argument(target_node, 'item_type')} data"
        if source_type == "construct_list" and connection_type != list_type_for_item(node_argument(source_node, "item_type")):
            return f"construct_list output requires {list_type_for_item(node_argument(source_node, 'item_type'))} data"
        if target_type == "list_append":
            expected_type = (
                list_type_for_item(node_argument(target_node, "item_type"))
                if to_port == "list-in"
                else node_argument(target_node, "item_type")
            )
            if connection_type != expected_type:
                return f"list_append {to_port} requires {expected_type} data"
        if source_type == "list_append" and connection_type != list_type_for_item(node_argument(source_node, "item_type")):
            return f"list_append output requires {list_type_for_item(node_argument(source_node, 'item_type'))} data"
        if target_type == "foreach" and (connection_type != list_type_for_item(node_argument(target_node, "item_type")) or to_port != "list-in"):
            return f"foreach input requires {list_type_for_item(node_argument(target_node, 'item_type'))} data"
        if source_type == "foreach" and (connection_type != node_argument(source_node, "item_type") or from_port != "item-out"):
            return f"foreach output requires {node_argument(source_node, 'item_type')} data"
        if source_type == "llm" and from_port == "tool_calls" and connection_type != "list-content":
            return "llm tool_calls output requires list-content data"
        return None
    except (KeyError, StopIteration, TypeError):
        return "connection does not match the node contract"
```

### agent/workflow_validator.py

```python
def _validate_node(node: Any, index: int, structs: dict[str, Any] | None = None) -> None:
    structs = structs or {}
    if not isinstance(node, dict):
        raise WorkflowValidationError(f"nodes[{index}] must be an object")
    node_id = node.get("id")
    if not isinstance(node_id, str) or not node_id:
        raise WorkflowValidationError(f"nodes[{index}].id must be a non-empty string")
    node_type = node.get("type")
    if node_type not in SUPPORTED_NODE_TYPES:
        raise WorkflowValidationError(f"unsupported node type: {node_type}")
    arguments = node.get("arguments", {})
    if not isinstance(arguments, dict):
        raise WorkflowValidationError(f"nodes[{index}].arguments must be an object")
    misplaced_arguments = (NODE_ARGUMENT_FIELDS - {"function_id"}).intersection(node)
    if misplaced_arguments:
        fields = ", ".join(sorted(misplaced_arguments))
        raise WorkflowValidationError(
            f"nodes[{index}] configurable fields must be inside arguments: {fields}"
        )
    misplaced_shared_fields = NODE_SHARED_FIELDS.intersection(arguments)
    if misplaced_shared_fields:
        fields = ", ".join(sorted(misplaced_shared_fields))
        raise WorkflowValidationError(
            f"nodes[{index}] shared fields must be top-level: {fields}"
        )
    unknown_arguments = set(arguments) - NODE_ARGUMENT_FIELDS_BY_TYPE[node_type]
    if unknown_arguments:
        fields = ", ".join(sorted(unknown_arguments))
        raise WorkflowValidationError(
            f"nodes[{index}].arguments contains unsupported fields: {fields}"
        )
    unknown_fields = set(node) - NODE_BASE_FIELDS - NODE_SHARED_FIELDS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise WorkflowValidationError(
            f"nodes[{index}] contains unsupported top-level fields: {fields}"
        )
    _validate_declared_data_inputs(node, index)

    if node_type in {"input", "output"}:
        _validate_workflow_ports(node, index)

    if node_type == "router":
        branches = node_argument(node, "branches")
        if not isinstance(branches, list):
            raise WorkflowValidationError(f"nodes[{index}].arguments.branches must be a list")
        branch_ids = [
            branch.get("id") if isinstance(branch, dict) else None
            for branch in branches
        ]
        branch_names = [
            branch.get("name") if isinstance(branch, dict) else None
            for branch in branches
        ]
        if any(not isinstance(branch_id, str) or not branch_id for branch_id in branch_ids):
            raise WorkflowValidationError(
                f"nodes[{index}].branches must contain non-empty ids"
            )
        if any(
            not isinstance(branch_name, str) or not branch_name
            for branch_name in branch_names
        ):
            raise WorkflowValidationError(
                f"nodes[{index}].branches must contain non-empty names"
            )
        if len(branch_ids) != len(set(branch_ids)):
            raise WorkflowValidationError(f"nodes[{index}].branches contains duplicate ids")
        if "branch$others" in branch_ids:
            raise WorkflowValidationError(
                f"nodes[{index}].branches reserves id 'branch$others' for the built-in fallback"
            )
        if len(branch_names) != len(set(branch_names)):
            raise WorkflowValidationError(
                f"nodes[{index}].branches contains duplicate names"
            )
        if any(not isinstance(branch, dict) for branch in branches):
            raise WorkflowValidationError(
                f"nodes[{index}].branches items must be objects"
            )
        for branch in branches:
            if set(branch) - {"id", "name"}:
                raise WorkflowValidationError(
                    f"nodes[{index}].branches contains unsupported fields"
                )
    elif node_type == "llm":
        if node_argument(node, "tools_source", "declared") not in {"declared", "definitions"}:
            raise WorkflowValidationError("llm tools_source must be 'declared' or 'definitions'")
    elif node_type == "construct_tool":
        from workflow_tools import validate_construct_tool_arguments
        try:
            validate_construct_tool_arguments(arguments)
        except ValueError as error:
            raise WorkflowValidationError(f"construct_tool node {node_id}: {error}") from error
    elif node_type == "construct_message":
        if node_argument(node, "role_source", "fixed") not in {"fixed", "port"}:
            raise WorkflowValidationError(
                "construct_message node role_source must be 'fixed' or 'port'"
            )
        if node_argument(node, "role", "user") not in {
            "system",
            "user",
            "assistant",
            "tool",
        }:
            raise WorkflowValidationError(
                "construct_message node role must be a supported message role"
            )
    elif node_type == "construct_content":
        _validate_construct_content(node)
    elif node_type == "construct_map_content":
        _validate_construct_map_content(node)
    elif node_type == "deserialize_json":
        outputs = node_argument(node, "outputs")
        if not isinstance(outputs, list) or not outputs or any(
            not isinstance(output, dict)
            or set(output) != {"key", "type"}
            or not isinstance(output.get("key"), str)
            or not output["key"]
            or output["key"] == "control-out"
            or output.get("type") not in DATA_CONNECTION_TYPES
            for output in outputs
        ):
            raise WorkflowValidationError(
                "deserialize_json outputs must contain valid key and type fields"
            )
        output_keys = [output["key"] for output in outputs]
        if len(output_keys) != len(set(output_keys)):
            raise WorkflowValidationError(
                "deserialize_json outputs contains duplicate keys"
            )
    elif node_type == "construct_list":
        _validate_construct_list(node, structs)
    elif node_type in {"list_length", "list_get", "list_slice"}:
        value_type = node_argument(node, "value_type")
        if not isinstance(value_type, str) or not value_type.startswith("list-") or not _valid_item_type(value_type[5:], structs):
            raise WorkflowValidationError(f"{node_type} value_type must be a supported list type")
        if node_type == "list_slice":
            for name in ("start", "stop", "step"):
                if node_argument(node, f"{name}_source", "port") not in {"fixed", "port"}:
                    raise WorkflowValidationError(f"list_slice {name}_source must be 'fixed' or 'port'")
                value = node_argument(node, name)
                if value is not None:
                    if not is_number_value(value) or (isinstance(value, float) and not value.is_integer()):
                        raise WorkflowValidationError(f"list_slice {name} must be an integer or null")
                    if name == "step" and value == 0:
                        raise WorkflowValidationError("list_slice step cannot be zero")
        if node_type == "list_get":
            source = node_argument(node, "index_source", "port")
            if source not in {"fixed", "port"}:
                raise WorkflowValidationError("list_get index_source must be 'fixed' or 'port'")
            index = node_argument(node, "index")
            if source == "fixed" or "index" in node.get("arguments", {}):
                if not is_number_value(index) or (isinstance(index, float) and not index.is_integer()):
                    raise WorkflowValidationError("list_get index must be an integer")
    elif node_type == "list_append":
        if not _valid_item_type(node_argument(node, "item_type"), structs):
            raise WorkflowValidationError(
                "list_append node item_type must be 'content' or a declared Struct"
            )
        if node_argument(node, "position") not in {"start", "end"}:
            raise WorkflowValidationError(
                "list_append node position must be 'start' or 'end'"
            )
    elif node_type == "foreach":
        if not _valid_item_type(node_argument(node, "item_type"), structs):
            raise WorkflowValidationError(
                "foreach node item_type must be 'content' or a declared Struct"
            )
    elif node_type in {"context_create", "context_read", "context_write", "session_create", "session_read", "session_write", "while_pop"}:
        value_type = node_argument(node, "value_type")
        is_context = node_type in {"context_create", "context_read", "context_write", "while_pop"}
        if value_type not in DATA_CONNECTION_TYPES and not (is_context and _valid_local_type(value_type, structs)):
            raise WorkflowValidationError(
                "context node value_type must be a supported data type"
            )
        if node_type == "while_pop":
            if not isinstance(value_type, str) or not value_type.startswith("list-") or not _valid_item_type(value_type[5:], structs):
                raise WorkflowValidationError("while_pop value_type must be a supported list type")
            if node_argument(node, "position", "end") not in {"start", "end"}:
                raise WorkflowValidationError("while_pop position must be 'start' or 'end'")
        if node_type == "context_create":
            context_id = node_argument(node, "context_id")
            if context_id is not None and (
                not isinstance(context_id, str) or not context_id.strip()
            ):
                raise WorkflowValidationError(
                    "context_create context_id must be a non-empty string"
                )
        if node_type in {"context_read", "context_write", "while_pop"}:
            source = node_argument(node, "context_id_source", "port")
            context_id = node_argument(node, "context_id")
            if source not in {"port", "fixed"}:
                raise WorkflowValidationError(
                    "context node context_id_source must be 'port' or 'fixed'"
                )
            if source == "fixed" and (
                not isinstance(context_id, str) or not context_id.strip()
            ):
                raise WorkflowValidationError(
                    "context node context_id must be a non-empty string when using a fixed ID"
                )
    elif node_type == "construct_struct":
        sid = node_argument(node, "struct_id")
        if sid not in structs:
            raise WorkflowValidationError(f"construct_struct references unknown Struct: {sid}")
        if set(node.get("dataInputPorts", [])) != {field["name"] for field in structs[sid]["fields"]}:
            raise WorkflowValidationError("construct_struct dataInputPorts must match declared fields")
    elif node_type == "struct_get":
        sid, field_name = node_argument(node, "struct_id"), node_argument(node, "field")
        definition = structs.get(sid)
        if definition is None or field_name not in {field["name"] for field in definition["fields"]}:
            raise WorkflowValidationError("struct_get must reference a declared Struct field")
        if node_argument(node, "missing", "error") not in {"error", "fallback"}:
            raise WorkflowValidationError("struct_get missing must be error or fallback")
        selected = next(field for field in definition["fields"] if field["name"] == field_name)
        fallback_enabled = node_argument(node, "has_fallback", False)
        if fallback_enabled != (node_argument(node, "missing", "error") == "fallback"):
            raise WorkflowValidationError("struct_get has_fallback must match missing mode")
        if fallback_enabled and selected["required"]:
            raise WorkflowValidationError("struct_get fallback is only valid for optional fields")
        expected_inputs = {"struct-in"} | ({"fallback-in"} if fallback_enabled else set())
        if set(node.get("dataInputPorts", [])) != expected_inputs:
            raise WorkflowValidationError("struct_get dataInputPorts must match its fallback mode")
    elif node_type == "struct_update":
        sid = node_argument(node, "struct_id")
        definition = structs.get(sid)
        if definition is None:
            raise WorkflowValidationError(f"struct_update references unknown Struct: {sid}")
        fields = {field["name"]: field for field in definition["fields"]}
        updates, removals = node_argument(node, "updates", []), node_argument(node, "remove_fields", [])
        if not isinstance(updates, list) or not isinstance(removals, list) or len(updates) != len(set(updates)) or len(removals) != len(set(removals)):
            raise WorkflowValidationError("struct_update fields must be unique lists")
        if any(name not in fields for name in updates + removals):
            raise WorkflowValidationError("struct_update references an unknown field")
        if any(fields[name]["required"] for name in removals):
            raise WorkflowValidationError("struct_update cannot remove required fields")
        if set(updates) & set(removals):
            raise WorkflowValidationError("struct_update cannot update and remove the same field")
        if set(node.get("dataInputPorts", [])) != set(updates) | {"struct-in"}:
            raise WorkflowValidationError("struct_update dataInputPorts must match updates")
    elif node_type in {"struct_to_json", "json_to_struct"}:
        value_type = node_argument(node, "value_type")
        if not isinstance(value_type, str) or not value_type.startswith(("struct:", "list-struct:")) or not _valid_local_type(value_type, structs):
            raise WorkflowValidationError(f"{node_type} requires a declared Struct type")
    elif node_type == "tool":
        if node_argument(node, "mode", "sync") != "sync":
            raise WorkflowValidationError("tool only supports sync mode; use remote_async_tool")
        # Reuse remote validation for typed ports, timeouts and callbacks.
        arguments = dict(node.get("arguments", {}))
        arguments.pop("mode", "sync")
        callback = arguments.pop("callback", None)
        outputs = arguments.pop("outputs", [])
        if callback is not None:
            raise WorkflowValidationError("sync tool cannot configure callback")
        arguments["outputs"] = outputs
        proxy = {**node, "type": "remote_sync_tool", "arguments": arguments}
        _validate_node(proxy, index, structs)
    elif node_type == "local_tool":
        parameters = node_argument(node, "parameters", [])
        if not isinstance(parameters, list) or any(
            not isinstance(parameter, str) or not parameter or parameter == "control-in"
            for parameter in parameters
        ):
            raise WorkflowValidationError(
                "tool node parameters must be non-empty strings other than control-in"
            )
        if len(parameters) != len(set(parameters)):
            raise WorkflowValidationError("tool node parameters contains duplicates")
        tool_name = node_argument(node, "tool")
        if not isinstance(tool_name, str) or not tool_name:
            raise WorkflowValidationError("tool node tool must be a non-empty string")
    elif node_type in {"remote_sync_tool", "remote_async_tool"}:
        parameters = node_argument(node, "parameters", [])
        if not isinstance(parameters, list) or any(
            not isinstance(parameter, dict)
            or set(parameter) != {"name", "type"}
            or not isinstance(parameter.get("name"), str)
            or not parameter["name"]
            or parameter["name"] == "control-in"
            or parameter.get("type") not in DATA_CONNECTION_TYPES
            for parameter in parameters
        ):
            raise WorkflowValidationError("remote tool parameters must contain valid name and type fields")
        parameter_names = [parameter["name"] for parameter in parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise WorkflowValidationError("tool node parameters contains duplicate names")
        tool_name = node_argument(node, "tool")
        if not isinstance(tool_name, str) or not tool_name:
            raise WorkflowValidationError("tool node tool must be a non-empty string")
        if node_type == "remote_sync_tool":
            outputs = node_argument(node, "outputs", [])
            if not isinstance(outputs, list) or any(
                not isinstance(output, dict)
                or set(output) != {"name", "type"}
                or not isinstance(output.get("name"), str)
                or not output["name"]
                or output["name"] == "control-out"
                or output.get("type") not in DATA_CONNECTION_TYPES
                for output in outputs
            ):
                raise WorkflowValidationError("remote sync tool outputs must contain valid name and type fields")
            output_names = [output["name"] for output in outputs]
            if len(output_names) != len(set(output_names)):
                raise WorkflowValidationError("remote sync tool outputs contains duplicate names")
        timeout_ms = node_argument(node, "timeout_ms")
        if timeout_ms is not None and (
            not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0
        ):
            raise WorkflowValidationError("remote tool timeout_ms must be a positive integer")
        maximum_env = (
            "TOOL_CLIENT_MAX_WAIT_MS"
            if node_type == "remote_sync_tool"
            else "TOOL_CLIENT_MAX_ASYNC_TIMEOUT_MS"
        )
        default_maximum = "10000" if node_type == "remote_sync_tool" else "3600000"
        maximum_ms = int(os.getenv(maximum_env, default_maximum))
        if timeout_ms is not None and timeout_ms > maximum_ms:
            raise WorkflowValidationError(
                f"remote tool timeout_ms must not exceed {maximum_ms}"
            )
        if node_type == "remote_async_tool":
            callback = node_argument(node, "callback")
            if callback is not None and (
                not isinstance(callback, dict)
                or set(callback) != {"type", "queue", "event_type", "on"}
                or callback.get("type") != "redis"
                or not isinstance(callback.get("queue"), str)
                or not callback["queue"]
                or len(callback["queue"]) > 256
                or not isinstance(callback.get("event_type"), str)
                or not callback["event_type"]
                or len(callback["event_type"]) > 128
                or not isinstance(callback.get("on"), list)
                or not callback["on"]
                or not all(isinstance(status, str) for status in callback["on"])
                or any(status not in {"working", "completed", "failed"} for status in callback["on"])
                or len(callback["on"]) != len(set(callback["on"]))
            ):
                raise WorkflowValidationError("remote async tool callback must be a valid Redis callback")
    elif node_type == "spawn_and_wait_subprocess":
        if "input_ports" in node or "output_ports" in node:
            raise WorkflowValidationError("subprocess interface snapshots are no longer supported; connect workflow-file and arguments-json")

def _validate_declared_data_inputs(node: dict[str, Any], index: int) -> None:
    declared_inputs = node.get("dataInputPorts", [])
    if not isinstance(declared_inputs, list) or any(
        not isinstance(port_id, str) or not port_id for port_id in declared_inputs
    ):
        raise WorkflowValidationError(
            f"nodes[{index}].dataInputPorts must be a list of non-empty strings"
        )
    if len(declared_inputs) != len(set(declared_inputs)):
        raise WorkflowValidationError(
            f"nodes[{index}].dataInputPorts contains duplicate ports"
        )

def _validate_workflow_ports(node: dict[str, Any], index: int) -> None:
    if node.get("workflowPorts") is None:
        raise WorkflowValidationError(
            f"nodes[{index}].workflowPorts is required for {node['type']} nodes"
        )
    ports = node.get("workflowPorts", [])
    if not isinstance(ports, list):
        raise WorkflowValidationError(f"nodes[{index}].workflowPorts must be a list")
    port_ids = []
    port_names = []
    for port_index, port in enumerate(ports):
        if not isinstance(port, dict):
            raise WorkflowValidationError(
                f"nodes[{index}].workflowPorts[{port_index}] must be an object"
            )
        port_id = port.get("id")
        name = port.get("name")
        if not isinstance(port_id, str) or not port_id.startswith("workflow:"):
            raise WorkflowValidationError(
                f"nodes[{index}].workflowPorts[{port_index}].id must use the workflow: namespace"
            )
        if not isinstance(name, str) or not name or port_id != f"workflow:{name}":
            raise WorkflowValidationError(
                f"nodes[{index}].workflowPorts[{port_index}] id must match its name"
            )
        if port.get("type") not in DATA_CONNECTION_TYPES:
            raise WorkflowValidationError(
                f"nodes[{index}].workflowPorts[{port_index}].type is unsupported"
            )
        port_ids.append(port_id.casefold())
        port_names.append(name.strip().casefold())
    if len(port_ids) != len(set(port_ids)) or len(port_names) != len(set(port_names)):
        raise WorkflowValidationError(f"nodes[{index}].workflowPorts contains duplicates")

def _validate_construct_content(node: dict[str, Any]) -> None:
    append_items = node_argument(node, "append_items", [])
    if not isinstance(append_items, list) or not append_items:
        raise WorkflowValidationError(
            "construct_content node append_items must be a non-empty list"
        )
    port_ids = []
    for index, item in enumerate(append_items):
        if not isinstance(item, dict) or item.get("type") not in {"port", "fixed"}:
            raise WorkflowValidationError(
                f"construct_content node append_items[{index}] must be a port or fixed item"
            )
        if item["type"] == "port":
            port_id = item.get("port_id")
            if not isinstance(port_id, str) or not port_id:
                raise WorkflowValidationError(
                    f"construct_content node append_items[{index}].port_id must be a non-empty string"
                )
            port_ids.append(port_id)
        elif not isinstance(item.get("value", ""), str):
            raise WorkflowValidationError(
                f"construct_content node append_items[{index}].value must be a string"
            )
    if set(node.get("dataInputPorts", [])) != set(port_ids):
        raise WorkflowValidationError(
            "construct_content node dataInputPorts must match port append_items"
        )
    if len(port_ids) != len(set(port_ids)):
        raise WorkflowValidationError(
            "construct_content node port append_items must have unique port_id values"
        )

def _validate_construct_map_content(node: dict[str, Any]) -> None:
    mappings = node_argument(node, "mappings")
    if not isinstance(mappings, list) or not mappings:
        raise WorkflowValidationError("construct_map_content mappings must be a non-empty list")
    keys = []
    port_ids = []
    for index, item in enumerate(mappings):
        if not isinstance(item, dict) or not isinstance(item.get("key"), str) or not item["key"]:
            raise WorkflowValidationError(
                f"construct_map_content mappings[{index}] must contain a non-empty string key"
            )
        keys.append(item["key"])
        if item.get("value_source", "fixed") == "port":
            if set(item) != {"key", "value_source", "port_id"}:
                raise WorkflowValidationError(
                    f"construct_map_content mappings[{index}] port values require port_id only"
                )
            port_id = item.get("port_id")
            if not isinstance(port_id, str) or not port_id or port_id in {"control-in", "control-out"}:
                raise WorkflowValidationError(
                    f"construct_map_content mappings[{index}].port_id must be a non-empty data port ID"
                )
            port_ids.append(port_id)
        elif item.get("value_source", "fixed") == "fixed":
            if set(item) not in ({"key", "value"}, {"key", "value_source", "value"}) or not isinstance(item.get("value"), str):
                raise WorkflowValidationError(
                    f"construct_map_content mappings[{index}] fixed values require a string value"
                )
        else:
            raise WorkflowValidationError(
                f"construct_map_content mappings[{index}].value_source must be 'fixed' or 'port'"
            )
    if len(keys) != len(set(keys)):
        raise WorkflowValidationError("construct_map_content mappings contains duplicate keys")
    if len(port_ids) != len(set(port_ids)):
        raise WorkflowValidationError("construct_map_content port mappings must have unique port_id values")
    if set(node.get("dataInputPorts", [])) != set(port_ids):
        raise WorkflowValidationError(
            "construct_map_content node dataInputPorts must match port mappings"
        )

def _validate_construct_list(node: dict[str, Any], structs: dict[str, Any] | None = None) -> None:
    structs = structs or {}
    item_type = node_argument(node, "item_type")
    if not _valid_item_type(item_type, structs):
        raise WorkflowValidationError(
            "construct_list node item_type must be 'content' or a declared Struct"
        )
    initial_value_count = node_argument(node, "initial_value_count")
    if (
        not isinstance(initial_value_count, int)
        or isinstance(initial_value_count, bool)
        or not 0 <= initial_value_count <= 20
    ):
        raise WorkflowValidationError(
            "construct_list node initial_value_count must be an integer from 0 to 20"
        )
    expected_inputs = {
        f"{item_type}-in-{input_index}"
        for input_index in range(initial_value_count)
    }
    if set(node.get("dataInputPorts", [])) != expected_inputs:
        raise WorkflowValidationError(
            "construct_list node dataInputPorts must match item_type and initial_value_count"
        )
```

### agent/workflow_functions.py

```python
def bind_function_interfaces(workflow: dict[str, Any]) -> dict[str, Any]:
    """Return an independent document with function ports resolved from metadata."""
    workflow = copy.deepcopy(workflow)
    definitions = validate_struct_definitions(workflow.get("metadata", {}).get("structs", []))
    functions = {}
    names = set()
    for function in workflow.get("metadata", {}).get("functions", []):
        fid, name = function["id"], function["name"]
        if not STRUCT_ID.fullmatch(fid) or fid in functions:
            raise ValueError(f"duplicate or invalid function id: {fid}")
        if not name.strip() or name.strip().casefold() in names:
            raise ValueError(f"duplicate or empty function name: {name}")
        for side in ("input_ports", "output_ports"):
            seen = set()
            for port in function[side]:
                if not port["name"].strip() or port["name"] in seen:
                    raise ValueError(f"function {fid} has duplicate or empty {side}")
                if not is_internal_type(port["type"], definitions):
                    raise ValueError(f"function {fid} has unknown port type: {port['type']}")
                seen.add(port["name"])
        functions[fid] = function
        names.add(name.strip().casefold())
    for node in workflow["nodes"]:
        kind = node["type"]
        if kind in {"function_input", "function_output"}:
            function_id = node.get("function_id")
            if function_id is None:
                raise ValueError(f"{kind} must belong to a function")
            if function_id not in functions:
                raise ValueError(f"node {node['id']} references unknown function: {function_id}")
            side = "input_ports" if kind == "function_input" else "output_ports"
            node["function_ports"] = copy.deepcopy(functions[function_id][side])
        elif kind == "function_call":
            target = node_argument(node, "function_id")
            if target not in functions:
                raise ValueError(f"function_call references unknown function: {target}")
            for side in ("input_ports", "output_ports"):
                if side in node and node[side] != functions[target][side]:
                    raise ValueError(f"function_call {node['id']} has stale {side}")
                node[side] = copy.deepcopy(functions[target][side])
        # Legacy body ownership is unnecessary: only boundaries identify a
        # function at runtime. Validation infers membership from control edges.
        if kind not in {"function_input", "function_output"}:
            node.pop("function_id", None)
    return workflow
```

### agent/workflow_tools.py

```python
def validate_parameters(schema: Any) -> None:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("schema must be a JSON Schema object with type 'object'")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError(f"invalid parameter schema: {error.message}") from error
    required = schema.get("required", [])
    if any(name not in schema.get("properties", {}) for name in required):
        raise ValueError("required must reference names in schema.properties")

def validate_tool(tool: Any) -> dict[str, Any]:
    if not isinstance(tool, dict) or tool.get("type") != "function":
        raise ValueError("tool must be an object with type 'function'")
    function = tool.get("function")
    if not isinstance(function, dict):
        raise ValueError("tool.function must be an object")
    name = function.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("tool name must be a non-empty string")
    if "description" in function and not isinstance(function["description"], str):
        raise ValueError("tool description must be a string")
    validate_parameters(function.get("parameters"))
    return tool

def build_tool(name: Any, description: Any, schema: Any, required: Any = None) -> dict[str, Any]:
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except ValueError as error:
            raise ValueError("schema contains invalid JSON") from error
    parameters = copy.deepcopy(schema)
    if required is not None:
        if not isinstance(required, list) or any(not isinstance(item, str) or not item for item in required):
            raise ValueError("required must be a list of non-empty parameter names")
        if len(required) != len(set(required)):
            raise ValueError("required must not contain duplicate names")
        if not isinstance(parameters, dict):
            raise ValueError("schema must be a JSON Schema object")
        parameters["required"] = list(required)
    return validate_tool({"type": "function", "function": {
        "name": name, "description": description, "parameters": parameters,
    }})

def validate_construct_tool_arguments(arguments: dict[str, Any]) -> None:
    for field in TOOL_FIELDS:
        if arguments.get(f"{field}_source", "fixed") not in ("fixed", "port"):
            raise ValueError(f"construct_tool {field}_source must be 'fixed' or 'port'")
    fixed = lambda field: arguments.get(f"{field}_source", "fixed") == "fixed"
    name = arguments.get("tool_name", "") if fixed("tool_name") else "dynamic_tool"
    description = arguments.get("description", "") if fixed("description") else ""
    schema = arguments.get("schema", TOOL_DEFAULTS["schema"]) if fixed("schema") else {"type": "object"}
    required = arguments.get("required") if fixed("required") else None
    if fixed("required") and "required" in arguments and required is None:
        raise ValueError("construct_tool required must be a list of parameter names")
    # When schema comes from a port, required names can only be checked at runtime.
    if not fixed("schema") and isinstance(required, list):
        schema = {"type": "object", "properties": {name: {} for name in required if isinstance(name, str)}}
    build_tool(name, description, schema, required)
```

## Repository workflow-json skill snapshot

---
name: workflow-json
description: Design executable AAgent Workflow 2.0 JSON without repository access.
---

# AAgent Workflow JSON Design

Generate complete executable Workflow 2.0 JSON. Assume only this skill and user input are available. This is a durable **process-scheduled** workflow language, not a generic DAG or API sequence. Return valid JSON in one fenced `json` block. Never emit pseudo-nodes, comments, invented types, or runtime process records.

## Missing external facts

Infer ordinary choices conservatively. Ask only when missing information blocks execution or materially changes behavior. Never invent registered Tool names/contracts, required model identifiers, existing child-workflow filenames/contracts, or user approval policy. A dynamic child filename may be supplied at runtime; do not require a static declaration. When creating both parent and child, choose explicit filenames and use them consistently. `metadata.tools` declares an expected contract; it does not register/install a Tool. Ask for missing facts or avoid that dependency. Never claim testing or registration without evidence.

## Process runtime model

A Workflow run is a durable process. A scheduler executes one node at a time from a ready queue and persists progress.

- Waiting nodes return a scheduling request. The process becomes `blocked` with a `wait_for` condition and re-enters the ready queue only on a matching event. Waiting does not occupy a worker.
- `wait_terminal_event` blocks for a **new** user-message event on this process terminal. Earlier messages do not satisfy it. Assistant output does not wake it. It has no data output and does not consume the message.
- `read_terminal_input`, after wake, returns all saved user message bodies in chronological order as `list-content`, not just the waking message.
- `output_to_terminal` appends non-empty text and continues; it does not wake a waiter. Emit a prompt before waiting when appropriate.
- `spawn_and_wait_subprocess` reads a filename and JSON arguments from data inputs, creates a distinct child process and terminal, and blocks the parent until child exit. On success it emits the full result object as JSON text and continues through control-out. On child failure/termination, a connected error-out resumes the parent with error-json. Invalid argument JSON, arguments that violate the child input interface, and missing target files use the same error path immediately without creating a child or blocking. Without that branch, failure propagates to the parent.
- The scheduler persists a pending child call. Resume validates results against the child's saved compiled output interface, fills result-json on success or error-json on a handled child failure/termination, and advances to the selected successor without executing the spawn node again or reloading the target file. Do not add a manual restart, polling loop, or Context handoff to return the result. Worker-crash side-effect guarantees remain separate.
- Parent/child may share a public terminal but have separate internal process identities. Never serialize process IDs, wait conditions, scheduler status, compiled graphs, logs, or checkpoints.
- Context is durable cross-node/process state. A process owns Context it creates; a child may access ancestor Context, but parent cannot access a child's Context. Context is cleaned with process termination. Session has separate semantics.
- Active execution timeout excludes blocked/queued time. Do not model human waits as long-running LLM/Tool calls or assume side effects are exactly-once after worker crash.

## Root contract

```json
{
  "schema_version": "2.0",
  "description": "Purpose",
  "metadata": {"structs": [], "tools": [], "functions": []},
  "input_ports": [],
  "output_ports": [],
  "nodes": [],
  "connections": []
}
```

- Required keys: `schema_version`, `input_ports`, `output_ports`, `nodes`, `connections`. Version is string `"2.0"`. Always include `connections`, even empty. Include description and metadata when useful. Do not emit subprocess_workflow_files or workflow_nodes at root or under metadata. No root `name`; filename is external.
- Port is exactly `{ "name":"...", "type":"..." }`; names non-empty and unique per side after trim/case-fold.
- Types: `content` (string), `number` (finite JSON number, not boolean), `list-content` (string array), `map-content` (string-to-string object), `struct:<Id>`, `list-struct:<Id>`. Struct IDs match `[A-Za-z_][A-Za-z0-9_]*` and must be declared in `metadata.structs`.
- Struct is forbidden on root, Tool, and child interfaces. Convert to JSON `content` at those boundaries.
- Node IDs unique/non-empty. Only documented node types, arguments, and fields. Configuration belongs in `arguments`; optional `name`, numeric `x`,`y` are presentation-only. Never include compiled fields (`data_inputs`, `successors`, `_workflow_result`).
- Exactly one `input` and at least one `output`. Their `workflowPorts` mirror root ports exactly and in order: `[{"id":"workflow:<name>","name":"<name>","type":"<type>"}]`.
- Node shape: `{ "id":"...", "type":"...", "arguments":{...} }` plus permitted shared fields; omit empty arguments. Connection shape: `{ "fromId":"...", "fromPortId":"...", "toId":"...", "toPortId":"...", "type":"..." }` (optional `id` omitted). Type is `control` or exact data type at both endpoints.
- At runtime, Input receives values supplied when the process is created. Output collects connected, provided values matching `output_ports` and ends that graph/process frame.

## Control and data

Normal nodes have `control-in`,`control-out`; Input only `control-out`, Output only `control-in`. Control orders execution; data edges propagate values independently.

- Every node is control-reachable from the unique Input. Control graph is a tree: no merges, shared nodes between branches, or cycles except loop-back to its owner.
- Each control output/input has at most one edge. Required control ports connect. Every Router branch, including fallback, connects.
- Each data input has at most one producer. Missing runtime-required input fails; `null` counts as missing. Draw data edges even when control passes through the producer.
- Data may flow from ancestor scope into nested scope, not child-to-parent, between sibling branches, or between loop iterations. Use Context for loop results.
- Branches do not reconverge. Give each terminal branch its own Output or redesign.

### Router

Requires `arguments.branches:[{"id":"branch_id","name":"exact-match"}]`. `content-in:content` selects exact name. Each branch ID is a control output. Fixed `branch$others` fallback is always present and not listed in branches; connect it. No generic `control-out`. Missing/non-string input fails; unmatched string takes fallback.

### Loops

`foreach` and `while_pop` use `control-in`,`loop-out`,`loop-in`,`control-out`. Connect loop-out to first body node and last body node back to this loop's loop-in. Connect control-out to post-loop node. Empty list goes directly to control-out. Body is linear: no Router/multi-output node, Output, shared node, or other entry. A spawn_and_wait_subprocess with unconnected error-out remains valid in an existing linear body; move a call with both success/error branches into a local function if handling inside an iteration.

- `foreach`: required `item_type` (`content` or declared `struct:<Id>`); `list-in:list-<item_type>`; `item-out:<item_type>` is in loop scope.
- `while_pop`: required `value_type` (`list-content` or declared `list-struct:<Id>`); pops one item/iteration from a Context-backed list and outputs `item-out` of item type. Defaults `position:"end"`, `context_id_source:"port"`. Port mode requires `context-id:content`; fixed mode requires nonblank `context_id`. It does not output the mutated list.
- If an iteration needs branching or a multi-control-output node, keep the loop body as one `function_call` and put that logic in a local function. Function control flow has its own validated region; do not connect its branches back into the caller except through the declared function return.

## Node reference

Unless noted, nodes use ordinary control ports. Data port names below include types.

| Type | Required arguments | Data ports / semantics |
|---|---|---|
| `input` | none | outputs root `workflow:<name>` |
| `output` | none | inputs root `workflow:<name>`; ends graph |
| `router` | `branches` | `content-in`; special control ports above |
| `construct_message` | none | `content-in` -> `content-out` Message JSON; optional inputs `reasoning-in:content`, `tool-calls-in:list-content` (assistant only), `tool-call-id-in:content` (tool only); optional `role` (system/user/assistant/tool, default user), `role_source` (fixed default or port; port adds `role-in`) |
| `construct_content` | `append_items` | nonempty ordered concat -> `content-out`; items `{type:"fixed",value:string}` or `{type:"port",port_id:string}`; port IDs unique and equal `dataInputPorts`; missing runtime values skipped |
| `construct_map_content` | `mappings` | nonempty mappings -> `map-out`; unique key and fixed string value, or `value_source:"port"` plus unique `port_id`; port IDs equal `dataInputPorts`, runtime values strings |
| `map_content_get` | none | `map-in:map-content`,`key-in:content` -> `content-out:content`; missing key fails |
| `number_to_content` | none | `number-in:number` -> `content-out:content` |
| `output_to_terminal` | none | `content-in:content`; appends nonempty text |
| `wait_terminal_event` | none | no data ports; blocks on new user message; does not return/consume it |
| `read_terminal_input` | none | `list-out:list-content`; all saved user messages oldest-first |
| `deserialize_json` | nonempty `outputs:[{key,type}]` | `content-in` JSON object -> configured outputs; unique keys, built-in types, keys required; non-string content JSON-serialized |
| `construct_list` | `item_type`,`initial_value_count` | count 0..20; inputs `<item_type>-in-N`; `list-out:list-<item_type>`; item type content or declared Struct |
| `list_append` | `item_type`,`position` | `list-in:list-<item_type>`,`item-in:<item_type>` -> same list type; position start/end |
| `list_length` | `value_type` | `list-in` -> `length-out:number`; list-content or declared list-struct |
| `list_get` | `value_type` | `list-in` -> `item-out`; `index_source` default port or fixed; port adds `index-in:number`; fixed requires integer `index` |
| `list_slice` | `value_type` | `list-in` -> same `list-out`; list-content or list-struct. Optional start/stop/step source/value; port adds matching `*-in:number` |
| `construct_tool` | none | outputs `tool-out:content`; optional `tool_name`,`description`,`schema`,`required`, each with optional `<field>_source` (`fixed`/`port`). Port inputs: `name-in`,`description-in`,`schema-in` (JSON Schema text), `required-in:list-content`. Builds one function Tool definition; schema must be an object-parameter JSON Schema |
| `foreach`,`while_pop` | as above | special loop control ports |
| `llm` | none | `messages-in:list-content` (nonempty JSON-string list of `{role,content}`) -> `output:content`; optional `model`,`think`,`tool_calls`,`tools`,`tools_source`. `tool_calls:true` adds `tool_calls:list-content` output and `available-tools-in:list-content` input (or `tools-in:list-content` with `tools_source:"definitions"`). Provider/model external. Generated tool calls are not executed automatically |
| `tool` | `tool`,`parameters:[{name,type}]`,`outputs:[{name,type}]` | synchronous registered Tool. Ports exactly match `metadata.tools` declaration (`kind` local/remote). Optional `mode` only sync, `timeout_ms`, `callback` only null |
| `json_tool` | none | `tool-name:content`,`arguments-json:content` -> `result-json:content` on `control-out`; on exception outputs `error-json:content` and takes `error-out` if connected, otherwise process fails. Invokes a dynamically named registered Local/Remote Tool; it does not create a child process |
| `remote_async_tool` | `tool` | async Remote Tool; declared params, output `task_id:content`; optional parameters/timeout_ms/callback; requires remote declaration; not a workflow subprocess |
| `local_tool` (legacy) | `tool` | optional string-array parameters; each content input; `output:content`. Prefer unified `tool` |
| `remote_sync_tool` (legacy) | `tool` | parameters/outputs port arrays, optional timeout_ms. Prefer unified `tool` |
| `context_create` | `value_type` | `initial-value:<type>` -> `context-id:content`; optional nonblank unique `context_id`; omit to generate |
| `context_read` | `value_type` | -> `value-out:<type>`; default port ID mode requires `context-id:content`; fixed mode requires nonblank `context_id` |
| `context_write` | `value_type` | `value-in:<type>` and port-mode context-id -> `context-id:content`,`value-out:<type>`; ID mode as context_read |
| `session_create` | `value_type` | `initial-value:<type>` -> `session-id:content` |
| `session_read` | `value_type` | `session-id:content` -> `value-out:<type>` |
| `session_write` | `value_type` | `session-id:content`,`value-in:<type>` -> `session-id:content`,`value-out:<type>` |
| `spawn_and_wait_subprocess` | none | `workflow-file:content`, `arguments-json:content` -> `result-json:content` on control-out; optional error-out with `error-json:content`; creates and waits for a child process |

## Contracts and composition

- Struct entry: `{"id":"Record","name":"Record","color":"#336699","fields":[{"name":"title","type":"content","required":true}]}`. IDs/field names use identifier syntax; fields unique; types built-in or declared Struct; recursion forbidden. Struct values are validated objects; list-struct is a list of objects.
- Struct nodes if needed: `construct_struct` (`struct_id`, required fields by name -> `struct-out`); `struct_get` (`struct_id`,`field`, optional `missing:"error"|"fallback"`, `has_fallback` default false; `struct-in`, optional `fallback-in` -> `value-out`); `struct_update` (`struct_id`, optional `updates`,`remove_fields`; `struct-in` -> `struct-out`); `struct_to_json` (`value_type`,`value-in` -> JSON `content-out`); `json_to_struct` (`value_type`,`content-in` -> `value-out`). Declare Struct first.
- Context allows built-in/declared Struct; Session built-in only. Context IDs are exact strings, never normalize. Port mode default; fixed mode has no ID input and requires nonblank `context_id`.
- Tool declaration: `metadata.tools:[{"name":"...","kind":"local|remote","input_ports":[{"name":"...","type":"content"}],"output_ports":[{"name":"...","type":"content"}]}]`. Types only content/number/list-content/map-content; no Struct/control names. Declaration is not proof of registration; node arrays copy it exactly.
- `llm.messages-in` is a list of JSON-encoded messages, not a raw prompt. Build via `construct_message` and compatible list flow; use a system message for system instructions. Exact model/provider is external.
- To save an assistant turn, use one `construct_message(role="assistant")`: connect LLM `output` (normalize null to empty content if necessary) to `content-in`, `reasoning` to `reasoning-in`, and `tool_calls` directly to `tool-calls-in`. The call input is a list of JSON strings; the node parses each into an object, preserving call IDs and argument strings. Empty calls and absent optional inputs are omitted. Reasoning is retained even without calls. Do not build different message shapes using a required-field Struct and a plain-message branch.
- For a tool result, use `construct_message(role="tool")` with result text on `content-in` and the original assistant call ID on `tool-call-id-in`. Always supply this ID for native tool results. Optional message fields are role-specific; passing reasoning/calls to a non-assistant, or a tool-call ID to a non-tool, fails. Existing role/content-only messages remain supported.
- LLM tools may come from `metadata.tools` (`tools_source:"declared"`, the default) or complete function definitions supplied as JSON strings in `tools-in:list-content` (`tools_source:"definitions"`). The latter does not require pre-registration when merely offered to the model. To execute a model-selected call, explicitly route/parse and invoke a Tool node or `json_tool`; `llm.tool_calls` alone only returns call descriptions. `json_tool` success/error control branches are separate scopes, so never pass data from one branch into the other or out to a parent scope.
- Local functions are not processes. Declare `metadata.functions` entries `{id,name,input_ports,output_ports}`. Each has exactly one `function_input` and at least one `function_output`, with top-level `function_id` matching declaration. Control goes entry-to-return. Call with `function_call` and `arguments.function_id`; data ports `function:<name>`. Each invocation has isolated state; return only via function outputs. No recursive calls; each node belongs to one main/function region.
## Child workflows and terminal interaction

- Use one node: `{"id":"call-child","type":"spawn_and_wait_subprocess","arguments":{}}` (empty arguments may be omitted). Connect control-in/control-out and optionally error-out. It has no configuration fields, child declarations, or input_ports/output_ports snapshots. Old workflow_file/workflow_name arguments and per-port calls require explicit JSON rewiring; removing old declarations alone does not convert them.
- Connect `workflow-file:content` to an exact workspace filename including its extension (nonblank, at most 200 characters). Preserve the exact string; do not substitute a repository path. Supply it from a parent input or a construct_content node with a fixed filename. Runtime loading checks the target and rejects recursive calls.
- Connect `arguments-json:content` to JSON **object text**, for example `{"name":"小明"}`. Keys match the target's root input_ports names; unknown keys or non-null values of the wrong type fail. Missing/null values count as unprovided. With dynamic targets, validation uses the interface loaded at call time, not an author-time snapshot. An empty input interface still needs `{}` text.
- `result-json:content` contains the full child output object as JSON text, for example `{"reply":"你好，小明！"}`. The child receives values through Input and returns through Output. To extract reply, use deserialize_json with `arguments:{"outputs":[{"key":"reply","type":"content"}]}`, connect result-json to content-in, and use its reply output. Forward result-json directly when the full object is wanted.
- To recover from a child that fails or is terminated, connect error-out to a separate handler and error-json to that handler's data input. Error JSON is an object with workflow_file, process_id, status (failed/terminated), and error (string); deserialize_json with key error and type content extracts the message for output_to_terminal or another handler. Leave error-out unconnected to preserve failure propagation. Success and error branches have separate scopes and must terminate separately; result-json is only available on success and error-json only on the error path. Errors before child creation (including invalid/non-object argument JSON, unknown argument names, wrong argument types, and missing target workflow files) also emit error-json and select error-out; their process_id is null and status is failed, and no child or pending call is created. Missing/null arguments retain the input interface semantics and are treated as not supplied. If error-out is not connected these errors fail the parent. Invalid child result contracts still fail the current process directly. Handled invocation and child errors are retained in the call trace while the parent may complete successfully.
- For dynamic JSON parameters, build a declared Struct and serialize with struct_to_json, or use an already serialized object input. Do not concatenate arbitrary user strings into JSON; quotes and newlines need correct escaping. Struct values must be serialized before crossing the process interface. Context remains available for explicit shared state; result-json already handles the return value.
- When the requested workflow is interactive, connect terminal nodes explicitly. A runnable one-message pattern is: prompt via output_to_terminal → wait_terminal_event → read_terminal_input → list_get with `arguments:{"value_type":"list-content","index_source":"fixed","index":-1}` → spawn_and_wait_subprocess → deserialize_json → output_to_terminal → Output. Connect the terminal reader's list-out to list-in, the selected item-out to arguments-json, and a filename producer to workflow-file. The prompt should ask for a JSON object such as `{"name":"小明"}`; print the decoded reply in the parent terminal. This handles one message and ends; do not imply it is a continuing chat loop. Prompt and filename text need actual producers and control edges.
- Terminal I/O serves user interaction; child Input/Output serves process parameters and results. A child does not need to reread terminal history to receive arguments, and printing to its terminal does not return a value to the parent. Keep Input and Output boundary nodes even for terminal-driven workflows, using empty root input_ports when creation-time inputs are unnecessary.

## Design and validation

1. Extract purpose, inputs, outputs, dependencies, side effects, interaction, failure, repetition, and stop conditions.
2. Resolve only necessary external facts; make other reasonable choices.
3. Choose the smallest structure: ordinary nodes, Router, finite Foreach, Context, terminal wait+read, or a real subprocess.
4. Declare ports, Structs, Tool contracts, and local functions before nodes. Child calls use fixed JSON ports and runtime filename/argument producers; do not declare child snapshots.
5. Sketch control tree first; independently terminate branches. Add loop-backs, then typed data edges.
6. Check node arguments/ports/types, persistence over waits, and behavior on every path.
7. Without validator/runtime, say the result is statically reasoned, not executed.

Final checklist:

- [ ] Pure valid JSON; version exactly `"2.0"`; required root keys present.
- [ ] Exactly one Input, at least one Output; unique IDs; supported nodes/arguments only.
- [ ] Root snapshots exact and ordered; no Struct on public interfaces.
- [ ] Required controls connected; every node reachable; no merge/illegal cycle; Router branches and fallback terminate separately.
- [ ] Loop body linear and returns to owner; no Router/Output/branching; item does not escape scope.
- [ ] Data endpoints/types match; no duplicate producer or illegal cross-scope edge.
- [ ] Runtime-required values exist on all paths and match JSON types.
- [ ] Terminal wait has an appropriate prompt and explicit read after wake.
- [ ] Context/Session types and ID modes correct; loop results use Context as needed.
- [ ] External dependencies supplied or resolved at runtime; Tool/function declarations match; no fabricated registration claims.
- [ ] Child calls have workflow-file and JSON object text on arguments-json, consume result-json on success or error-json via an optional separate error-out handler, and contain no legacy declarations, filename arguments, or interface snapshots.
- [ ] Output, empty-input, branch, and failure behavior meet request.

If a blocking external fact is missing, ask a focused question instead of fabricating an executable workflow. Add a concise note for assumptions or unverified dependencies.


## Experiment design experience

# 本实验的工作流修改经验

这份记录来自本实验的实现与回归测试，供 main 迭代器作为设计参考。它不是新的 Workflow 语法，不代表额外工具已注册，也不是 ALFWorld 环境真值或已证明有效的解题策略。以 `workflow-json` 规范、当前 main 的真实绑定和迭代器的能力限制为准。

## 1. 先弄清楚改变的对象

- “更新经验文档”和“修改工作流”是两种不同操作。看实际写入目标和内容，不根据 iterator、evolution 等名称判断。
- 调整任务启发式、提示词或节点结构前，先定位证据：是规则错误、输入解析错误、数据流错误，还是工具或供应商故障？供应商暂时失败不证明需要重写算法。
- 能用局部改动解决时，不重写整张图；需要改变控制逻辑时，可以改变节点和连线，不必把所有变化挤进经验文本。没有可靠改进依据时，返回原 main 是合理结果。

## 2. 修改结构时同时检查控制流与数据流

- “排在前面”不等于数据已传到后面。新节点需要正确的控制边和类型匹配的数据边；移除或替换节点时也要处理原有消费者。
- 分支不能任意合流。需要统一返回值时，把分支封装在本地函数中，由各分支分别返回。循环体有分支时，也优先把单次迭代放进本地函数。
- 函数内外通过明确输入输出传值。Context 用于确实需要跨轮次保存或共享更新的状态，不要为普通中间结果添加一层状态存储。
- 直接连接兼容端口；需要结构化 JSON 时用声明的 Struct 和序列化节点，不要靠手拼字符串处理引号、换行和可选字段。

## 3. 保护绑定，而不只是保护文件名

- main 的输入输出是 bootstrap 的调用契约。修改内部实现时保持这个契约，不能顺手改返回字段或类型。
- 模型 ID、经验文件 ID 和子流程名称都是部署绑定，不是示例占位符。重新生成模板不应把有效绑定重置成默认值。
- 只固定读取工具的名称并不足够：还要保护其文件 ID 来源及输入依赖链，防止重新接线后读取另一个文件。
- 本实验只允许 main 内的受限改动；不根据设计参考中的通用示例新增工具、终端、Session 或子流程能力，也不修改 stable-main、bootstrap、iterator 或权限。

## 4. 将模型提案与写入操作分开

- 模型输出完整候选 JSON；固定流程负责校验、checkpoint 和写入。不要让模型自行决定写入目标、revision 或是否跳过校验。
- JSON 能解析只是第一层。还要验证 schema、节点参数、端口类型、控制结构、函数作用域、调用契约和能力边界，再编译。
- 校验通过表示候选在这些检查范围内可接受，不表示任务更容易成功，更不表示已经运行过。禁止把静态通过写成性能提升结论。
- 本实验每轮只提出一次候选。无改动就不写 main；无效候选保留旧 main，记录拒绝原因，不进入无限修复循环。

## 5. checkpoint 与并发写入是两道不同的保护

- 在修改 main 前保存 checkpoint，才能找到迭代前的版本；checkpoint 本身不是并发锁。
- 提案应对应生成时读取的 revision；校验时重新检查，写回时仍使用 revision 条件。有人同时修改了 main，就丢弃过期提案，不强行覆盖。
- main 和经验的两次顺序写入不是事务。main 已保存、随后经验更新失败时，不能声称两者都未改变或已自动一起回滚。
- 具备整工作区恢复权限，不等于实际调用了整工作区恢复。当前自动恢复只针对 main 历史内容；不能把它描述成 main 与经验的配对恢复。

## 6. 日志保存事实增量，不递归复制自己

- 模型决策需要的完整历史与审计日志分开。每轮日志记录新增观察、动作、reasoning、状态和错误，不反复复制累计历史。
- 除消息协议或接口明确要求 JSON 字符串的边界外，保留对象和数组的结构，避免反复序列化已经编码的内容，导致大量反斜杠。
- 不把包含日志文件自身内容的完整 workspace diff 再写回这个日志。记录 checkpoint、文件 ID、revision 等定位信息，需要时查询差异。
- 区分三类结果：环境任务成功与否、工作流运行成功与否、main 候选是否被采用。`updated` 只表示写入了新版本，不代表新版本更好。

## 7. 用行为验证改动，明确证据边界

- 有测试环境时，至少验证一次真实结构改动能保存，且下一轮确实执行新结构；只检查生成 JSON 中出现某个词不够。
- 检查无改动、非法候选、过期 revision、checkpoint 失败，以及新 main 运行失败后恢复旧版本的路径。拒绝或失败不能静默覆盖其他版本。
- 区分图的静态编译、真实调度配合模拟模型的测试、真实供应商联调和真实环境效果评估。只报告实际完成的层级。
- 本地修改、导入工作区文件、加载运行时工具和更新权限是不同步骤。修改了本地 `.flow` 不代表在线流程已更新；不要据此声称已部署。

## 提交候选前自查

1. 改动对应哪条记录中的什么问题，为什么应修改 main 而不是仅修改经验？
2. 是否保留接口、绑定、经验读取依赖和能力边界？
3. 控制边、数据边、分支返回、循环状态和缺失值是否完整？
4. 能否用更小的改动得到同样效果？没有证据时是否应保持不变？
5. 是否混淆了“可编译”“已采用”“能运行”和“效果更好”？


## Source fingerprints


- `agent/workflow_2_0.schema.json`: `980e150af00b929ba52b9f24fc54939202c13911ef2b0056f90c0820e7a139e0`

- `agent/workflow_contract.py`: `459ff3707a5c27ad336a452cf666d9475a49c61bbfb933ef165ecb3b9e5f6c9d`

- `agent/workflow_validator.py`: `3d65dce379e5265377917a65fdbfbd143472a32de722fff26bda088029d49a74`

- `agent/workflow_functions.py`: `caaa24e2f7ac351cc03ba15a0aa4250bd16bafe7708318014992542388576ae6`

- `agent/workflow_tools.py`: `11784cfae7e315899ced6c266de5c9710ac6293d743e1e45c8010a1f8654dc87`

- `agent/workflow_evolution.py`: `ef8caad6f78d9d963f1e899ecf280a3233792e0334ef7655eb9415fdc4534b8f`

- `skills/workflow-json/SKILL.md`: `ae24159205ddd2c42d1839ba2c805958c8dfe0a57f9f1e6936cbc8cc9c7f69c1`

- Node types: 40. Regenerate with `python experiments/alfworld-recovery-scope/build_workflow_reference.py`.
