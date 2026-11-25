# Workflow 2.0 node/schema reference (experiment-local)

This is a standalone workspace Markdown file. Required permission: read=1,
write=4. The iterator reads this file at runtime and must not edit it.

## Authority and scope

- Current runtime declarations/schema and semantic checks below override stale
  examples or prose. The bundled experiment skill replaces the legacy repository
  skill; it does not append conflicting historical instructions. Only listed node types exist;
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

## Actual workspace tool contracts (from runtime decorators)

These are extracted from @tool on the implemented Python handlers, not from workflow metadata. Metadata resolves local/remote routing only; the running agent must also have imported the handler. A bind-mounted source update does not reload an existing Python process.

Workflow content ports carry strings; number ports carry numeric values. The revision input comes from workspace.get_file's integer revision without stringification. Named tool outputs are mapped individually by workflow_local_tool. prepare_main_update is read-only: ready means accepted for a later CAS update, unchanged means no executable change, rejected includes a validation error. HTTP/ACL errors and missing handlers raise; they are not candidate rejection results.

```json
{
  "workspace.list_files": {
    "handler": "list_workspace_files",
    "source": "agent_runtime/tools/workspace.py",
    "description": "列出工作区文件（不包含文件内容）",
    "inputSchema": {
      "type": "object",
      "properties": {},
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "type": "object"
          }
        },
        "revision": {
          "type": "integer"
        }
      },
      "required": [
        "items",
        "revision"
      ]
    }
  },
  "workspace.get_file": {
    "handler": "get_workspace_file",
    "source": "agent_runtime/tools/workspace.py",
    "description": "读取工作区文件内容和 revision",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_id": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "file_id"
      ],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object"
    }
  },
  "workspace.create_file": {
    "handler": "create_workspace_file",
    "source": "agent_runtime/tools/workspace.py",
    "description": "在工作区创建文件",
    "inputSchema": {
      "type": "object",
      "properties": {
        "name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200
        },
        "content": {
          "type": "string",
          "maxLength": 1000000
        }
      },
      "required": [
        "name"
      ],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object"
    }
  },
  "workspace.update_file": {
    "handler": "update_workspace_file",
    "source": "agent_runtime/tools/workspace.py",
    "description": "更新工作区文件名称或内容；必须使用最近读取到的 revision",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_id": {
          "type": "string",
          "minLength": 1
        },
        "name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200
        },
        "content": {
          "type": "string",
          "maxLength": 1000000
        },
        "revision": {
          "type": "integer",
          "minimum": 1
        }
      },
      "required": [
        "file_id",
        "name",
        "content",
        "revision"
      ],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object"
    }
  },
  "workspace.delete_file": {
    "handler": "delete_workspace_file",
    "source": "agent_runtime/tools/workspace.py",
    "description": "删除工作区文件；必须使用最近读取到的 revision",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_id": {
          "type": "string",
          "minLength": 1
        },
        "revision": {
          "type": "integer",
          "minimum": 1
        }
      },
      "required": [
        "file_id",
        "revision"
      ],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "deleted": {
          "type": "boolean"
        },
        "file_id": {
          "type": "string"
        }
      },
      "required": [
        "deleted",
        "file_id"
      ]
    }
  },
  "workspace.list_checkpoints": {
    "handler": "list_workspace_checkpoints",
    "source": "agent_runtime/tools/workspace.py",
    "description": "分页列出工作区 checkpoint，可按文件筛选；使用 next_before_seq 获取下一页",
    "inputSchema": {
      "type": "object",
      "properties": {
        "before_seq": {
          "type": "integer",
          "minimum": 1
        },
        "limit": {
          "type": "integer",
          "minimum": 1,
          "maximum": 100,
          "default": 50
        },
        "file_id": {
          "type": "string"
        }
      },
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "type": "object"
          }
        },
        "has_more": {
          "type": "boolean"
        },
        "next_before_seq": {
          "type": [
            "integer",
            "null"
          ]
        }
      },
      "required": [
        "items",
        "has_more",
        "next_before_seq"
      ]
    }
  },
  "workspace.checkpoint_tree": {
    "handler": "get_workspace_checkpoint_tree",
    "source": "agent_runtime/tools/workspace.py",
    "description": "读取工作区 checkpoint 分支树及当前 head_seq",
    "inputSchema": {
      "type": "object",
      "properties": {},
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "type": "object"
          }
        },
        "head_seq": {
          "type": [
            "integer",
            "null"
          ]
        }
      },
      "required": [
        "items",
        "head_seq"
      ]
    }
  },
  "workspace.get_parent_checkpoint": {
    "handler": "get_parent_workspace_checkpoint",
    "source": "agent_runtime/tools/workspace.py",
    "description": "获取 checkpoint 的父序号用于回滚；省略 seq 时查询当前 head。parent_seq=0 表示空工作区，可传给 restore_checkpoint；null 表示已无父 checkpoint",
    "inputSchema": {
      "type": "object",
      "properties": {
        "seq": {
          "type": "integer",
          "minimum": 0
        }
      },
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "seq": {
          "type": "integer",
          "minimum": 0
        },
        "parent_seq": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 0
        }
      },
      "required": [
        "seq",
        "parent_seq"
      ]
    }
  },
  "workspace.checkpoint_diff": {
    "handler": "get_workspace_checkpoint_diff",
    "source": "agent_runtime/tools/workspace.py",
    "description": "读取 checkpoint 相对于父 checkpoint 的文件差异；seq=0 表示空工作区",
    "inputSchema": {
      "type": "object",
      "properties": {
        "seq": {
          "type": "integer",
          "minimum": 0
        }
      },
      "required": [
        "seq"
      ],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "seq": {
          "type": "integer"
        },
        "parent_seq": {
          "type": [
            "integer",
            "null"
          ]
        },
        "changes": {
          "type": "array",
          "items": {
            "type": "object"
          }
        }
      },
      "required": [
        "seq",
        "parent_seq",
        "changes"
      ]
    }
  },
  "workspace.create_checkpoint": {
    "handler": "create_workspace_checkpoint",
    "source": "agent_runtime/tools/workspace.py",
    "description": "为当前工作区全部文件创建命名 checkpoint",
    "inputSchema": {
      "type": "object",
      "properties": {
        "name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200
        }
      },
      "required": [
        "name"
      ],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object"
    }
  },
  "workspace.restore_checkpoint": {
    "handler": "restore_workspace_checkpoint",
    "source": "agent_runtime/tools/workspace.py",
    "description": "将整个工作区恢复到指定 checkpoint，文件 revision 会更新；seq=0 会清空工作区",
    "inputSchema": {
      "type": "object",
      "properties": {
        "seq": {
          "type": "integer",
          "minimum": 0
        }
      },
      "required": [
        "seq"
      ],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object"
    }
  },
  "workspace.get_file_recovery_plan": {
    "handler": "get_file_recovery_plan",
    "source": "agent_runtime/tools/workspace.py",
    "description": "读取指定文件的逐级恢复计划：沿 checkpoint 当前分支跳过重复版本，以固定 stable 文件为底线；只读取，不执行恢复",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_id": {
          "type": "string",
          "minLength": 1
        },
        "stable_file_id": {
          "type": "string",
          "minLength": 1
        },
        "checkpoint_seq": {
          "type": "integer",
          "minimum": 0
        }
      },
      "required": [
        "file_id",
        "stable_file_id",
        "checkpoint_seq"
      ],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "versions": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "content": {
                "type": "string"
              },
              "checkpoint_seq": {
                "type": "integer",
                "minimum": 0
              },
              "source": {
                "enum": [
                  "checkpoint",
                  "stable"
                ]
              }
            },
            "required": [
              "content",
              "checkpoint_seq",
              "source"
            ],
            "additionalProperties": false
          }
        }
      },
      "required": [
        "versions"
      ]
    }
  },
  "workspace.prepare_main_update": {
    "handler": "prepare_workspace_main_update",
    "source": "agent_runtime/tools/workspace.py",
    "description": "只读校验 ALFWorld main 候选：检查版本、Workflow 2.0 编译、接口及只读能力边界，不执行也不写入候选",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_id": {
          "type": "string",
          "minLength": 1
        },
        "revision": {
          "type": "integer",
          "minimum": 0
        },
        "proposal": {
          "type": "string",
          "maxLength": 1000000
        }
      },
      "required": [
        "file_id",
        "revision",
        "proposal"
      ],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "status": {
          "type": "string"
        },
        "content": {
          "type": "string"
        },
        "error": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "revision": {
          "type": "integer"
        }
      },
      "required": [
        "status",
        "content",
        "error",
        "name",
        "revision"
      ]
    }
  }
}
```

## Exact runtime semantic validation and port rules (source excerpts)

### agent_runtime/workflow_contract.py

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

### agent_runtime/workflow_validator.py

```python
def validate_workflow(workflow: dict[str, Any]) -> None:
    if workflow.get("schema_version") != WORKFLOW_SCHEMA_VERSION:
        raise WorkflowValidationError(
            f"workflow.schema_version must be {WORKFLOW_SCHEMA_VERSION}"
        )
    _validate_workflow_schema(workflow)
    from workflow_functions import bind_function_interfaces
    try:
        workflow = bind_function_interfaces(workflow)
    except ValueError as error:
        raise WorkflowValidationError(str(error)) from error
    from workflow_structs import StructValidationError, is_internal_type, validate_struct_definitions
    try:
        structs = validate_struct_definitions(workflow.get("metadata", {}).get("structs", []))
    except (StructValidationError, AttributeError) as error:
        raise WorkflowValidationError(str(error)) from error
    nodes = workflow.get("nodes")
    connections = workflow.get("connections")
    if not isinstance(nodes, list):
        raise WorkflowValidationError("workflow.nodes must be a list")
    if not isinstance(connections, list):
        raise WorkflowValidationError("workflow.connections must be a list")
    input_ports = _validate_boundary_metadata(workflow, "input_ports")
    output_ports = _validate_boundary_metadata(workflow, "output_ports")
    for label, ports in (("input_ports", input_ports), ("output_ports", output_ports)):
        if any(port["type"].startswith(("struct:", "list-struct:")) for port in ports):
            raise WorkflowValidationError(f"workflow.{label} cannot expose Struct types; use JSON content")
    remote_tools = _validate_remote_tool_metadata(workflow)
    tools = _validate_tool_metadata(workflow)
    for tool in workflow.get("remote_tools", []):
        for port in tool.get("input_ports", []) + tool.get("output_ports", []):
            if port.get("type", "").startswith(("struct:", "list-struct:")):
                raise WorkflowValidationError("Tool interfaces cannot expose Struct types")

    node_by_id: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(nodes):
        _validate_node(node, index, structs)
        if node["type"] == "tool":
            declaration = tools.get(node_argument(node, "tool"))
            if declaration is None:
                raise WorkflowValidationError(f"nodes[{index}] tool is not registered in metadata.tools")
            if node_argument(node, "parameters") != declaration["input_ports"] or node_argument(node, "outputs") != declaration["output_ports"]:
                raise WorkflowValidationError(f"nodes[{index}] tool ports must match metadata.tools")
            if declaration["kind"] == "local" and node_argument(node, "mode", "sync") != "sync":
                raise WorkflowValidationError("local tool only supports sync mode")
        if node["type"] in {"remote_sync_tool", "remote_async_tool"}:
            declaration = (tools.get(node_argument(node, "tool")) if node["type"] == "remote_async_tool" else None) or remote_tools.get(node_argument(node, "tool"))
            if declaration is None:
                raise WorkflowValidationError(
                    f"nodes[{index}] remote tool is not registered in metadata.tools or workflow.remote_tools"
                )
            if declaration.get("kind", "remote") != "remote":
                raise WorkflowValidationError("remote_async_tool requires a remote tool declaration")
            if node_argument(node, "parameters") != declaration["input_ports"]:
                raise WorkflowValidationError(
                    f"nodes[{index}] remote tool inputs must match workflow.remote_tools"
                )
            if (
                node["type"] == "remote_sync_tool"
                and node_argument(node, "outputs") != declaration["output_ports"]
            ):
                raise WorkflowValidationError(
                    f"nodes[{index}] remote tool outputs must match workflow.remote_tools"
                )
        if node["type"] in {"input", "output"}:
            expected_ports = boundary_ports(
                input_ports if node["type"] == "input" else output_ports
            )
            if node.get("workflowPorts") != expected_ports:
                raise WorkflowValidationError(
                    f"nodes[{index}].workflowPorts must match workflow {node['type']}_ports"
                )
        node_id = node["id"]
        if node_id in node_by_id:
            raise WorkflowValidationError(f"duplicate node id: {node_id}")
        node_by_id[node_id] = node

    input_count = sum(node["type"] == "input" for node in nodes)
    if input_count != 1:
        raise WorkflowValidationError(
            f"workflow must contain exactly one input node, found {input_count}"
        )
    if not any(node["type"] == "output" for node in nodes):
        raise WorkflowValidationError("workflow must contain at least one output node")

    groups, owners = _infer_function_groups(workflow, node_by_id)

    # Acyclic calls allow nesting while keeping this first version non-recursive.
    calls = {f["id"]: set() for f in workflow.get("metadata", {}).get("functions", [])}
    for node in nodes:
        if node["type"] == "function_call" and owners[node["id"]] is not None:
            calls[owners[node["id"]]].add(node_argument(node, "function_id"))
    complete, active = set(), set()
    for function_id in calls:
        pending = [(function_id, False)]
        while pending:
            fid, exiting = pending.pop()
            if exiting:
                active.remove(fid)
                complete.add(fid)
            elif fid in active:
                raise WorkflowValidationError(f"recursive function call is not supported: {fid}")
            elif fid not in complete:
                active.add(fid)
                pending.append((fid, True))
                pending.extend((target, False) for target in calls[fid])

    connected_control_inputs: dict[str, set[str]] = {
        node_id: set() for node_id in node_by_id
    }
    connected_control_outputs: dict[str, set[str]] = {
        node_id: set() for node_id in node_by_id
    }
    connected_data_inputs: set[tuple[str, str]] = set()

    for index, connection in enumerate(connections):
        if not isinstance(connection, dict):
            raise WorkflowValidationError(f"connections[{index}] must be an object")
        from_id = connection.get("fromId")
        to_id = connection.get("toId")
        if from_id not in node_by_id:
            raise WorkflowValidationError(
                f"connections[{index}].fromId references unknown node: {from_id}"
            )
        if to_id not in node_by_id:
            raise WorkflowValidationError(
                f"connections[{index}].toId references unknown node: {to_id}"
            )

        from_port = _port_id(connection, index, "fromPortId")
        to_port = _port_id(connection, index, "toPortId")
        connection_type = connection.get("type")
        source_node = node_by_id[from_id]
        target_node = node_by_id[to_id]
        if owners[from_id] != owners[to_id]:
            raise WorkflowValidationError(f"connections[{index}] crosses function boundary")
        if connection_type == "control":
            _validate_control_connection(
                source_node, from_port, target_node, to_port, index
            )
            if from_port in connected_control_outputs[from_id]:
                raise WorkflowValidationError(
                    f"control output has multiple successors: node {from_id}, port {from_port}"
                )
            connected_control_outputs[from_id].add(from_port)
            connected_control_inputs[to_id].add(to_port)
        elif connection_type in DATA_CONNECTION_TYPES or (
            isinstance(connection_type, str)
            and connection_type.startswith(("struct:", "list-struct:"))
        ):
            _validate_data_connection(
                source_node,
                from_port,
                target_node,
                to_port,
                connection_type,
                index,
                input_ports,
                output_ports,
                structs,
            )
            target_endpoint = (to_id, to_port)
            if target_endpoint in connected_data_inputs:
                raise WorkflowValidationError(
                    f"data input has multiple sources: node {to_id}, port {to_port}"
                )
            connected_data_inputs.add(target_endpoint)
        else:
            raise WorkflowValidationError(
                f"connections[{index}].type must be a supported control or data type"
            )

    _validate_branches_in_foreach(node_by_id, connections)

    for node_id, node in node_by_id.items():
        node_type = node["type"]
        required_data_ports: set[str] = set()
        if node_type == "construct_tool":
            from workflow_tools import TOOL_FIELDS, TOOL_PORTS
            required_data_ports = {TOOL_PORTS[field] for field in TOOL_FIELDS if node_argument(node, f"{field}_source", "fixed") == "port"}
        elif node_type == "llm" and node_argument(node, "tool_calls") is True and node_argument(node, "tools_source", "declared") == "definitions":
            required_data_ports = {"tools-in"}
        elif node_type == "function_call":
            required_data_ports = {f"function:{port['name']}" for port in node["input_ports"]}
        elif node_type == "function_output":
            required_data_ports = {f"function:{port['name']}" for port in node["function_ports"]}
        elif node_type == "while_pop" and node_argument(node, "context_id_source", "port") == "port":
            required_data_ports = {"context-id"}
        elif node_type == "construct_struct":
            sid = node_argument(node, "struct_id")
            required_data_ports = {field["name"] for field in structs[sid]["fields"] if field["required"]}
        elif node_type == "struct_get":
            required_data_ports = {"struct-in"}
            if node_argument(node, "missing", "error") == "fallback":
                required_data_ports.add("fallback-in")
        elif node_type == "struct_update":
            required_data_ports = {"struct-in", *node_argument(node, "updates", [])}
        elif node_type == "struct_to_json":
            required_data_ports = {"value-in"}
        elif node_type == "json_to_struct":
            required_data_ports = {"content-in"}
        missing_data = sorted(port for port in required_data_ports if (node_id, port) not in connected_data_inputs)
        if missing_data:
            raise WorkflowValidationError(f"required data ports must be connected: node {node_id}, ports {', '.join(missing_data)}")
        required_inputs, required_outputs = control_ports_for_node(node)
        missing_inputs = required_inputs - connected_control_inputs[node_id]
        missing_outputs = required_outputs - connected_control_outputs[node_id]
        if node_type in {"json_tool", "spawn_and_wait_subprocess"}:
            missing_outputs.discard("error-out")
        if missing_inputs or missing_outputs:
            missing = [
                *(f"input:{port_id}" for port_id in sorted(missing_inputs)),
                *(f"output:{port_id}" for port_id in sorted(missing_outputs)),
            ]
            raise WorkflowValidationError(
                f"control ports must be connected: node {node_id}, ports {', '.join(missing)}"
            )

    # Each function is a separate control tree and lifecycle root.
    for members in groups.values():
        edges = [edge for edge in connections if edge["fromId"] in members]
        _validate_lifecycles(members, edges)

def _validate_branches_in_foreach(
    nodes_by_id: dict[str, dict[str, Any]], connections: list[dict[str, Any]]
) -> None:
    control_edges = [connection for connection in connections if connection.get("type") == "control"]
    outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes_by_id}
    incoming: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes_by_id}
    for edge in control_edges:
        outgoing[edge["fromId"]].append(edge)
        incoming[edge["toId"]].append(edge)

    for foreach_id, foreach_node in nodes_by_id.items():
        if foreach_node["type"] not in {"foreach", "while_pop"}:
            continue

        pending = [edge["toId"] for edge in outgoing[foreach_id] if edge["fromPortId"] == "loop-out"]
        body: set[str] = set()
        while pending:
            node_id = pending.pop()
            if node_id == foreach_id or node_id in body:
                continue
            if len(outgoing[node_id]) > 1:
                raise WorkflowValidationError(
                    f"branching control flow is not allowed inside {foreach_node['type']}: node {node_id}"
                )
            body.add(node_id)
            for edge in outgoing[node_id]:
                target_id = edge["toId"]
                if target_id == foreach_id and edge["toPortId"] == "loop-in":
                    continue
                pending.append(target_id)

        for node_id in body:
            external_entries = [
                edge for edge in incoming[node_id]
                if edge["fromId"] not in body
                and not (edge["fromId"] == foreach_id and edge["fromPortId"] == "loop-out")
            ]
            if external_entries:
                raise WorkflowValidationError(
                    f"{foreach_node['type']} body node also has a control-flow entry from outside the loop: node {node_id}"
                )

def _infer_function_groups(workflow, node_by_id):
    """Infer static function membership by DFS; never annotate runtime nodes."""
    groups = {None: {}}
    roots = {None: next(n["id"] for n in node_by_id.values() if n["type"] == "input")}
    for function in workflow.get("metadata", {}).get("functions", []):
        fid = function["id"]
        entries = [n["id"] for n in node_by_id.values()
                   if n["type"] == "function_input" and n.get("function_id") == fid]
        if len(entries) != 1:
            raise WorkflowValidationError(f"function {fid} must contain exactly one function_input, found {len(entries)}")
        if not any(n["type"] == "function_output" and n.get("function_id") == fid
                   for n in node_by_id.values()):
            raise WorkflowValidationError(f"function {fid} must contain at least one function_output")
        roots[fid] = entries[0]
        groups[fid] = {}
    outgoing = {nid: [] for nid in node_by_id}
    for edge in workflow["connections"]:
        # Endpoint and port errors are reported by the regular connection checks.
        if (edge.get("type") == "control" and edge.get("fromId") in outgoing
                and edge.get("toId") in node_by_id):
            outgoing[edge["fromId"]].append(edge["toId"])
    owners = {}
    for owner, root in roots.items():
        pending = [root]
        while pending:
            nid = pending.pop()
            node = node_by_id[nid]
            if nid in owners:
                if owners[nid] != owner:
                    raise WorkflowValidationError(f"node {nid} is shared across function boundary")
                continue  # Loop back edges are checked by the lifecycle validator.
            if node["type"] in {"input", "output", "function_input", "function_output"}:
                boundary = node.get("function_id") if node["type"].startswith("function_") else None
                if boundary != owner:
                    raise WorkflowValidationError(f"control flow crosses function boundary at node {nid}")
            owners[nid] = owner
            groups[owner][nid] = node
            if node["type"] not in {"output", "function_output"}:
                # A function_call is an ordinary step here; do not enter its callee.
                pending.extend(outgoing[nid])
    # Keep unreachable nodes for the existing port/lifecycle diagnostics. They
    # cannot acquire function membership from legacy labels or data edges.
    for nid in node_by_id.keys() - owners.keys():
        owners[nid] = None
        groups[None][nid] = node_by_id[nid]
    return groups, owners

def _validate_lifecycles(
    nodes_by_id: dict[str, dict[str, Any]], connections: list[dict[str, Any]]
) -> None:
    """Check a control tree and visibility of values across branch/loop scopes.

    Scope paths are static compiler state only. Parents may supply descendants;
    a child or sibling may not supply its parent/sibling. Context operations are
    ordinary nodes: explicitly stored values cross boundaries via a later read.
    """
    Scope = tuple[tuple[str, str], ...]
    outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes_by_id}
    for edge in connections:
        if edge["type"] == "control":
            outgoing[edge["fromId"]].append(edge)

    node_scopes: dict[str, Scope] = {}
    output_scopes: dict[tuple[str, str], Scope] = {}
    active: set[str] = set()
    returned_loops: set[str] = set()
    input_id = next(node_id for node_id, node in nodes_by_id.items() if node["type"] in {"input", "function_input"})
    # Explicit DFS stack keeps maximum-sized trees independent of recursion limits.
    pending: list[tuple[str, Scope, str | None, bool]] = [(input_id, (), None, False)]
    while pending:
        node_id, scope, loop_id, exiting = pending.pop()
        if exiting:
            active.remove(node_id)
            continue
        if node_id in active:
            raise WorkflowValidationError(
                f"control-flow cycle is not a foreach loop-in return: node {node_id}"
            )
        if node_id in node_scopes:
            raise WorkflowValidationError(
                f"control-flow merge is not allowed: node {node_id} has multiple entries"
            )
        node = nodes_by_id[node_id]
        node_type = node["type"]
        _, control_outputs = control_ports_for_node(node)
        branching_outputs = control_outputs
        if node_type == "spawn_and_wait_subprocess" and not any(
            edge["fromPortId"] == "error-out" for edge in outgoing[node_id]
        ):
            # An unconnected optional error exit preserves existing linear loop bodies.
            branching_outputs = control_outputs - {"error-out"}
        if loop_id and (node_type == "router" or len(branching_outputs) > 1):
            raise WorkflowValidationError(
                f"branching control flow is not allowed inside {nodes_by_id[loop_id]['type']}: node {node_id}"
            )
        if loop_id and node_type in {"output", "function_output"}:
            raise WorkflowValidationError(
                f"{nodes_by_id[loop_id]['type']} body must return to loop-in instead of output: node {node_id}"
            )
        node_scopes[node_id] = scope
        active.add(node_id)
        pending.append((node_id, scope, loop_id, True))

        child_scopes = {}
        for port in control_outputs:
            child_scope = scope
            if node_type in {"foreach", "while_pop"} and port == "loop-out":
                child_scope = (*scope, (node_id, port))
                output_scopes[(node_id, "item-out")] = child_scope
            elif node_type not in {"foreach", "while_pop"} and (node_type == "router" or len(control_outputs) > 1):
                child_scope = (*scope, (node_id, port))
                if node_type in {"json_tool", "spawn_and_wait_subprocess"}:
                    data_port = "error-json" if port == "error-out" else "result-json"
                    output_scopes[(node_id, data_port)] = child_scope
            child_scopes[port] = child_scope

        for edge in reversed(outgoing[node_id]):
            port = edge["fromPortId"]
            child_scope = child_scopes[port]
            child_loop = node_id if node_type in {"foreach", "while_pop"} and port == "loop-out" else loop_id
            target_id = edge["toId"]
            if nodes_by_id[target_id]["type"] in {"foreach", "while_pop"} and edge["toPortId"] == "loop-in":
                if child_loop != target_id:
                    raise WorkflowValidationError(
                        f"{nodes_by_id[target_id]['type']} loop-in must return from its own body: node {target_id}, source {node_id}"
                    )
                returned_loops.add(target_id)
            else:
                pending.append((target_id, child_scope, child_loop, False))

    unreachable = sorted(set(nodes_by_id) - set(node_scopes))
    if unreachable:
        raise WorkflowValidationError(
            f"control-flow nodes are unreachable from input: {', '.join(unreachable)}"
        )
    for node_id, node in nodes_by_id.items():
        if node["type"] in {"foreach", "while_pop"} and node_id not in returned_loops:
            raise WorkflowValidationError(f"{node['type']} body has no loop-in return: node {node_id}")

    def describe(scope: Scope) -> str:
        return "root" + "".join(f" / {owner}:{port}" for owner, port in scope)

    for index, edge in enumerate(connections):
        if edge["type"] == "control":
            continue
        source = output_scopes.get((edge["fromId"], edge["fromPortId"]), node_scopes[edge["fromId"]])
        target = node_scopes[edge["toId"]]
        if target[:len(source)] != source:
            raise WorkflowValidationError(
                f"connections[{index}] crosses lifecycle boundary: "
                f"{edge['fromId']}.{edge['fromPortId']} [{describe(source)}] -> "
                f"{edge['toId']}.{edge['toPortId']} [{describe(target)}]; "
                "data source must belong to the same or an ancestor lifecycle"
            )

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

### agent_runtime/workflow_functions.py

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

### agent_runtime/workflow_parser.py

```python
def parse_workflow(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert ``nodes`` and ``connections`` to an index-linked node list.

    Control-flow links contain node indexes. Data inputs contain one mutable
    slot in the form ``[node_index, port_id, value_or_default]``; data outputs
    contain endpoint lists.
    """
    from workflow_functions import bind_function_interfaces
    workflow = bind_function_interfaces(workflow)
    if workflow.get("schema_version") != WORKFLOW_SCHEMA_VERSION:
        raise WorkflowParseError(
            f"unsupported workflow schema_version: {workflow.get('schema_version')!r}; "
            f"expected {WORKFLOW_SCHEMA_VERSION}"
        )
    nodes = workflow["nodes"]
    connections = workflow["connections"]
    input_ports = workflow["input_ports"]
    output_ports = workflow["output_ports"]
    from workflow_structs import validate_struct_definitions
    struct_definitions = validate_struct_definitions(workflow.get("metadata", {}).get("structs", []))
    function_names = {function["id"]: function["name"]
                      for function in workflow.get("metadata", {}).get("functions", [])}
    node_indexes = {node["id"]: index for index, node in enumerate(nodes)}
    linked_nodes: list[dict[str, Any]] = []
    for node in nodes:
        parsed_node = normalize_node_arguments(node)
        if node.get("type") == "function_input":
            parsed_node["_function_name"] = function_names[node["function_id"]]
        if node.get("type") in {"tool", "remote_async_tool"}:
            declaration = next((tool for tool in workflow.get("metadata", {}).get("tools", []) if tool["name"] == node_argument(node, "tool")), None)
            if declaration is None and node["type"] == "remote_async_tool":
                declaration = next((tool for tool in workflow.get("remote_tools", []) if tool["name"] == node_argument(node, "tool")), None)
            if declaration is None:
                raise WorkflowParseError("tool is not registered in metadata.tools")
            parsed_node["_tool_kind"] = declaration.get("kind", "remote")
        if node.get("type") == "llm":
            parsed_node["_metadata_tools"] = [
                {"name": tool["name"], "kind": tool.get("kind", "remote")}
                for tool in workflow.get("metadata", {}).get("tools", [])
            ]
        parsed_node.pop("x", None)
        parsed_node.pop("y", None)
        if node.get("type") == "input":
            parsed_node["workflowPorts"] = boundary_ports(input_ports)
        elif node.get("type") == "output":
            parsed_node["workflowPorts"] = boundary_ports(output_ports)
        node_input_ports, node_output_ports = data_ports_for_node(
            node, input_ports, output_ports
        )
        linked_nodes.append(
            {
                **parsed_node,
                "_struct_definitions": _node_struct_definitions(parsed_node, struct_definitions),
                "predecessors": {},
                "successors": {},
                "data_inputs": {
                    port_id: [None, None, None] for port_id in node_input_ports
                },
                "data_outputs": {port_id: [] for port_id in node_output_ports},
            }
        )

    for connection in connections:
        from_id = connection["fromId"]
        to_id = connection["toId"]
        from_index = node_indexes[from_id]
        to_index = node_indexes[to_id]
        from_port = connection["fromPortId"]
        to_port = connection["toPortId"]
        connection_type = connection["type"]
        if connection_type == "control":
            successor_key = _successor_key(linked_nodes[from_index], from_port)
            predecessor_key = _predecessor_key(linked_nodes[to_index], to_port)
            linked_nodes[from_index]["successors"][successor_key] = to_index
            linked_nodes[to_index]["predecessors"].setdefault(
                predecessor_key, []
            ).append(from_index)
        else:
            _append_output_endpoint(
                linked_nodes[from_index]["data_outputs"],
                from_port,
                [to_index, to_port],
            )
            linked_nodes[to_index]["data_inputs"][to_port] = [
                from_index,
                from_port,
                None,
            ]

    return linked_nodes
```

### agent_runtime/workflow_nodes.py

```python
def workflow_read_terminal_queue(current_id: int, workflow_map: WorkflowMap) -> int | WorkflowStep:
    from process_repository import read_terminal_input_queue
    from redis_client import get_connection
    from terminal_repository import current_terminal_process_id

    terminal_process_id = current_terminal_process_id.get()
    process = current_workflow_process.get()
    if not terminal_process_id or process is None:
        raise ValueError("read_terminal_queue requires a process terminal")
    node = workflow_map[current_id]
    successor = next_successor(node)
    contents = read_terminal_input_queue(get_connection(), terminal_process_id)
    if not contents:
        return WorkflowStep({"kind": "terminal_message", "process_id": terminal_process_id})
    propagate_workflow_output(workflow_map, node, "list-out", contents)
    return successor

def _json_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

def _deserialize_json_value(value: Any, value_type: str) -> Any:
    if value_type == "number" and is_number_value(value):
        return value
    if value_type == "content":
        return _json_content(value)
    if value_type == "list-content" and isinstance(value, list):
        return [_json_content(item) for item in value]
    if value_type == "map-content" and _is_map_content(value):
        return dict(value)
    raise ValueError(f"value does not match declared type {value_type}")

def workflow_deserialize_json(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    has_content, content = read_workflow_input(node, "content-in")
    if not has_content:
        raise ValueError(f"deserialize_json input is missing: node {node.get('id')}")
    if not isinstance(content, str):
        raise ValueError(f"deserialize_json input must be content: node {node.get('id')}")
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"deserialize_json input is invalid JSON: node {node.get('id')}") from error
    if not isinstance(document, dict):
        raise ValueError(f"deserialize_json root must be an object: node {node.get('id')}")

    converted = {}
    for output in node_argument(node, "outputs", []):
        key = output["key"]
        if key not in document:
            raise ValueError(f"deserialize_json key is missing: node {node.get('id')}, key {key}")
        try:
            converted[key] = _deserialize_json_value(document[key], output["type"])
        except ValueError as error:
            raise ValueError(
                f"deserialize_json value type mismatch: node {node.get('id')}, key {key}"
            ) from error

    for key, value in converted.items():
        propagate_workflow_output(workflow_map, node, key, value)
    return next_successor(node)

def workflow_struct_to_json(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_structs import validate_value
    node = workflow_map[current_id]
    present, value = read_workflow_input(node, "value-in")
    if not present: raise ValueError(f"struct_to_json input missing: node {node.get('id')}")
    value = validate_value(node_argument(node, "value_type"), value, _struct_defs(node))
    propagate_workflow_output(workflow_map, node, "content-out", json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return next_successor(node)

def workflow_json_to_struct(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_structs import validate_value
    node = workflow_map[current_id]
    present, content = read_workflow_input(node, "content-in")
    if not present or not isinstance(content, str): raise ValueError(f"json_to_struct content input invalid: node {node.get('id')}")
    try: value = json.loads(content)
    except json.JSONDecodeError as error: raise ValueError(f"json_to_struct invalid JSON: node {node.get('id')}") from error
    value = validate_value(node_argument(node, "value_type"), value, _struct_defs(node), copy_value=True)
    propagate_workflow_output(workflow_map, node, "value-out", value)
    return next_successor(node)

def workflow_foreach(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    items = node.get("_foreach_items")
    if items is None:
        has_items, input_items = read_workflow_input(node, "list-in")
        if not has_items:
            raise ValueError(f"foreach input is missing: node {node.get('id')}")
        if not isinstance(input_items, list):
            raise ValueError(f"foreach input must be a list: node {node.get('id')}")
        items = list(input_items)
        node["_foreach_items"] = items

    if not items:
        node.pop("_foreach_items", None)
        return next_successor(node)

    propagate_workflow_output(workflow_map, node, "item-out", items.pop(0))
    return next_successor(node, "item")

def workflow_while_pop(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_context_repository import pop_context

    node = workflow_map[current_id]
    context_id = node_argument(node, "context_id") if node_argument(node, "context_id_source", "port") == "fixed" else _context_input(node, "context-id", "Context ID 输入无效")
    has_item, item = pop_context(
        context_id,
        node["_workflow_invocation_id"],
        node_argument(node, "value_type"),
        node_argument(node, "position", "end"),
        _struct_defs(node),
        ancestor_invocation_ids=node.get("_workflow_ancestor_invocation_ids", ()),
    )
    if not has_item:
        return next_successor(node)
    propagate_workflow_output(workflow_map, node, "item-out", item)
    return next_successor(node, "item")

def workflow_router(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    has_key, key = read_workflow_input(node, "content-in")
    if not has_key:
        raise ValueError(f"router input is missing: node {node.get('id')}")
    branch_key = f"branch-{key}"
    if branch_key not in node.get("successors", {}):
        branch_key = "branch$others"
    return next_successor(node, branch_key)

def _tool_arguments(node: dict[str, Any]) -> dict[str, Any]:
    arguments = {}
    for parameter in tool_parameter_names(node):
        has_value, value = read_workflow_input(node, parameter)
        if has_value:
            if tool_parameter_type(node, parameter) == "number" and not is_number_value(value):
                raise ValueError(f"tool parameter {parameter} must match number")
            arguments[parameter] = value
    return arguments

def workflow_tool(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    if node_argument(node, "mode", "sync") != "sync":
        raise ValueError("tool only supports sync mode; use remote_async_tool")
    kind = node.get("_tool_kind")
    if kind == "local":
        if node_argument(node, "mode", "sync") != "sync":
            raise ValueError("local tool only supports sync mode")
        return workflow_local_tool(current_id, workflow_map)
    if kind == "remote":
        return workflow_remote_sync_tool(current_id, workflow_map)
    raise ValueError("tool kind must be resolved from metadata.tools")

def workflow_local_tool(current_id: int, workflow_map: WorkflowMap) -> int:
    from tools.tool import execute_tool

    node = workflow_map[current_id]
    result = execute_tool(
        node["id"], node_argument(node, "tool"), _tool_arguments(node), preserve_result=True
    )
    if node.get("type") == "local_tool":
        propagate_workflow_output(workflow_map, node, "output", _tool_output(result))
        return next_successor(node)

    outputs = node_argument(node, "outputs", [])
    if isinstance(result, dict):
        if len(outputs) == 1 and outputs[0]["name"] == "output" and "output" not in result:
            values = {"output": result}
        else:
            missing = [output["name"] for output in outputs if output["name"] not in result]
            if missing:
                raise ValueError(f"local tool result is missing outputs: {', '.join(missing)}")
            values = result
    elif len(outputs) == 1:
        values = {outputs[0]["name"]: result}
    elif outputs:
        raise ValueError("local tool result must be an object for named outputs")
    else:
        values = {}

    for output in outputs:
        name = output["name"]
        value = values[name]
        if output["type"] == "number" and not is_number_value(value):
            raise ValueError(f"local tool output {name} must match number")
        if output["type"] == "content":
            value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        elif output["type"] == "map-content" and not _is_map_content(value):
            raise ValueError(f"local tool output {name} must match map-content")
        propagate_workflow_output(workflow_map, node, name, value)
    return next_successor(node)
```

### agent_runtime/tools/tool.py

```python
def tool(description, parameters=None, name=None, output_schema=None):
    def register(function):
        tool_name = name or function.__name__
        if tool_name in tool_handlers:
            raise ValueError(f"工具已注册: {tool_name}")

        schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": description,
                "parameters": parameters or {"type": "object", "properties": {}}
            }
        }
        registered_tools.append(schema)
        tool_handlers[tool_name] = function
        registry_schema = {**schema, "outputSchema": output_schema}
        redis_register_tool(tool_name, registry_schema)
        return function

    return register

def execute_tool(id,tool,args,preserve_result=False):
    handler = tool_handlers.get(tool)
    if handler is None:
        raise ValueError(f"未知工具: {tool}")

    result = handler(**args)

    if preserve_result:
        return result

    # 将结果转为字符串（如果是列表等复杂类型，可做适当格式化）
    if isinstance(result, (list, dict)):
        result = json.dumps(result, ensure_ascii=False)
    elif result is None:
        result = "执行失败，未获取到数据"
    return str(result)
```

### agent_runtime/tools/workspace.py

```python
def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    base_url = os.getenv("WORKSPACE_API_URL", "http://agent_environment:8080").rstrip("/")
    headers = dict(kwargs.pop("headers", {}))
    try:
        from workflow_nodes import current_workflow_process

        process = current_workflow_process.get()
    except ImportError:
        process = None
    if process and process.get("process_id"):
        headers["X-AAgent-Process-ID"] = (
            f"{process['process_id']}:{process['_workspace_token']}"
        )
    try:
        response = requests.request(
            method,
            f"{base_url}/api/files{path}",
            timeout=(3, 15),
            headers=headers,
            **kwargs,
        )
    except requests.RequestException as error:
        raise RuntimeError(f"workspace request failed: {error}") from error

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.ok:
        detail = payload.get("error", payload.get("detail", payload))
        if response.status_code == 409:
            raise ValueError(f"workspace file revision conflict; read the file again: {detail}")
        if response.status_code == 404:
            resource = "checkpoint" if path.startswith("/checkpoints/") else "file"
            raise ValueError(f"workspace {resource} not found: {detail}")
        raise RuntimeError(f"workspace request failed with HTTP {response.status_code}: {detail}")
    if not isinstance(payload, dict):
        raise RuntimeError("workspace API returned an invalid response")
    return payload

def prepare_workspace_main_update(file_id: str, revision: int, proposal: str) -> dict[str, Any]:
    from workflow_evolution import prepare_main_update

    current = _request("GET", "/" + quote(file_id, safe=""))
    return prepare_main_update(current, revision, proposal)

def get_file_recovery_plan(file_id: str, stable_file_id: str, checkpoint_seq: int) -> dict[str, Any]:
    from workflow_recovery import build_file_recovery_plan

    return build_file_recovery_plan(file_id, stable_file_id, checkpoint_seq, _request)
```

### agent_runtime/workflow_recovery.py

```python
def build_file_recovery_plan(file_id, stable_file_id, checkpoint_seq, request):
    """Try each distinct earlier content once and stop at the stable anchor.

    All reads use the existing workspace API, including its file/checkpoint
    permission checks. Only the selected checkpoint's ancestors are considered.
    """
    if isinstance(checkpoint_seq, bool) or not isinstance(checkpoint_seq, int) or checkpoint_seq < 0:
        raise ValueError("checkpoint_seq must be a non-negative integer")
    current = request("GET", "/" + quote(file_id, safe=""))["content"]
    stable = request("GET", "/" + quote(stable_file_id, safe=""))["content"]
    if current == stable:
        return {"versions": []}
    versions = []
    seen_contents = {current}
    seen_checkpoints = set()
    cursor = checkpoint_seq
    while cursor:
        if cursor in seen_checkpoints:
            raise ValueError("checkpoint ancestry contains a cycle")
        seen_checkpoints.add(cursor)
        diff = request("GET", f"/checkpoints/{cursor}/diff")
        parent = diff["parent_seq"] or 0
        for change in diff["changes"]:
            previous = change.get("before_content")
            if change["file_id"] != file_id or previous is None or previous in seen_contents:
                continue
            seen_contents.add(previous)
            versions.append({"content": previous, "checkpoint_seq": parent,
                             "source": "stable" if previous == stable else "checkpoint"})
            if previous == stable:
                return {"versions": versions}
        cursor = parent
    # The immutable installation anchor is also usable when no older checkpoint
    # contains it (for example, an imported main with only one saved version).
    versions.append({"content": stable, "checkpoint_seq": 0, "source": "stable"})
    return {"versions": versions}
```

### agent_runtime/workflow_evolution.py

```python
def _check_capabilities(current: dict[str, Any], candidate: dict[str, Any]) -> None:
    for side in ("input_ports", "output_ports"):
        if candidate[side] != current[side]:
            raise ValueError(f"main {side} must remain unchanged")
    old_tools = current.get("metadata", {}).get("tools", [])
    if candidate.get("metadata", {}).get("tools", []) != old_tools:
        raise ValueError("main tool declarations must remain unchanged")
    # The shipped main may only read its bound experience file. Freeze the tool
    # and its entire data dependency chain, not merely a model-supplied file ID.
    old_nodes = {n["id"]: n for n in current["nodes"]}
    new_nodes = {n["id"]: n for n in candidate["nodes"]}
    protected = {n["id"] for n in current["nodes"] if n["type"] == "tool"}
    if {n["id"] for n in candidate["nodes"] if n["type"] == "tool"} != protected:
        raise ValueError("main cannot add or remove workspace tool nodes")
    for node_id in protected:
        if old_nodes[node_id].get("arguments", {}).get("tool") != "workspace.get_file":
            raise ValueError("main baseline must contain read-only workspace.get_file tools only")
    pending = list(protected)
    while pending:
        target = pending.pop()
        for edge in current["connections"]:
            if edge["type"] != "control" and edge["toId"] == target and edge["fromId"] not in protected:
                protected.add(edge["fromId"])
                pending.append(edge["fromId"])
    for node_id in protected:
        if node_id not in new_nodes or _without_layout(old_nodes[node_id]) != _without_layout(new_nodes[node_id]):
            raise ValueError(f"bound experience reader must remain unchanged: {node_id}")
        old_edges = [e for e in current["connections"] if e["type"] != "control" and e["toId"] == node_id]
        new_edges = [e for e in candidate["connections"] if e["type"] != "control" and e["toId"] == node_id]
        normalize = lambda edges: sorted(json.dumps({k: v for k, v in e.items() if k != "id"}, sort_keys=True) for e in edges)
        if normalize(old_edges) != normalize(new_edges):
            raise ValueError(f"bound experience reader wiring must remain unchanged: {node_id}")
    models = {n.get("arguments", {}).get("model") for n in current["nodes"] if n["type"] == "llm"}
    if not models or any(not isinstance(m, str) or not m or m.startswith("REPLACE_WITH_") for m in models):
        raise ValueError("main baseline requires concrete model bindings")
    if not any(n["type"] == "llm" for n in candidate["nodes"]):
        raise ValueError("main must retain an LLM decision node")
    for node in candidate["nodes"]:
        if node["type"] not in PURE_NODES:
            raise ValueError(f"main cannot use capability node {node['type']}")
        if node["type"] == "llm":
            args = node.get("arguments", {})
            if args.get("model") not in models:
                raise ValueError("main model bindings must remain unchanged")
            if args.get("tool_calls") is not False or args.get("tools"):
                raise ValueError("main LLM tool calls must remain disabled")

def prepare_main_update(current: dict[str, Any], revision: int, proposal: str) -> dict[str, Any]:
    """Return a checked candidate plus a CAS revision; rejection never mutates state."""
    result = {"status": "rejected", "content": "", "error": "",
              "name": current["name"], "revision": current["revision"]}
    try:
        if isinstance(revision, bool) or revision != current["revision"]:
            raise ValueError("main revision conflict; discard stale proposal and read main again")
        if not current["name"].endswith("-main.flow") or current["name"].endswith("-stable-main.flow"):
            raise ValueError("only a task main workflow can be evolved; stable-main is immutable")
        if not isinstance(proposal, str) or len(proposal) > 1_000_000:
            raise ValueError("candidate must be JSON text of at most 1000000 characters")
        text = proposal.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1)
        candidate = json.loads(text)
        if not isinstance(candidate, dict):
            raise ValueError("candidate must be a complete workflow JSON object")
        original = json.loads(current["content"])
        validate_workflow(candidate)
        _check_capabilities(original, candidate)
        parse_workflow(candidate)
        # Layout-only edits do not create new executable revisions.
        comparable = lambda doc: {**doc, "nodes": [_without_layout(n) for n in doc["nodes"]]}
        result["status"] = "unchanged" if comparable(original) == comparable(candidate) else "ready"
        result["content"] = json.dumps(candidate, ensure_ascii=False, indent=2) + "\n"
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        result["error"] = str(error)
    return result
```

### agent_runtime/workflow_tools.py

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

## Implementation-aligned workflow-json design skill

---
name: workflow-json-runtime
description: Design and revise this experiment's AAgent Workflow 2.0 JSON using the current runtime declarations, validator, compiler, and execution semantics.
---

# Workflow JSON design from the current implementation

Use the accompanying generated node/schema reference as the language definition.
Its catalog comes from `agent_runtime/workflow_contract.py`; its schema, semantic checks,
compiler and execution excerpts come from the current `agent_runtime/` implementation.
This skill describes how to use that material. It does not replace the code.
Do not import node names or ports from an older workflow skill or from memory.

## Design against the code

1. Preserve the current workflow's root input/output contract and concrete model
   and file bindings unless the task explicitly authorizes changing them.
2. Look up each node in the generated catalog. Copy its exact authored fields,
   argument allowlist, dynamic ports and accepted data connection types. Node
   fragments need the metadata shown alongside them; they are not complete graphs.
3. Declare structs/functions in metadata before using their types or IDs. Use
   `bind_function_interfaces` as the source for function boundary and call ports.
   Keep graph edges inside their function region; call functions through
   `function_call` and return through `function_output`.
4. Wire control edges for execution and data edges for values. A data edge alone
   does not schedule its target. Use `control_ports_for_node` for special branches
   and `connection_validation_error` for endpoint/type compatibility. Connect a
   router's `branch$others`. A control output has at most one successor.
5. Check the whole graph with `validate_workflow`, then compile it with
   `parse_workflow`. Per-node JSON Schema validation alone does not check graph
   lifecycles, function regions, loop bodies, required inputs or tool bindings.

Ordinary control ports are `control-in`/`control-out`, except where the catalog
says otherwise. Root boundary nodes require matching `workflowPorts`. Functions
use metadata-derived interfaces. Do not copy compiled `successors`, `data_inputs`,
`_struct_definitions`, scheduler state or function frames into authored JSON.

A loop has `control-in`, `loop-out`, `loop-in`, `control-out`. Wire the final body
node back to `loop-in` and the post-loop successor from `control-out`. The actual
`_validate_branches_in_foreach` check forbids multiple outgoing control edges and
external entries in a loop body. Put branching inside a called local function
when needed; do not wire the function's internal branches into the caller loop.

## Runtime values and terminal I/O

Use the runtime's declared types. `content` is text; JSON objects in a content
port are JSON text. `number` excludes booleans. Struct/list-struct types require
metadata and runtime field validation. Root/tool interfaces have their own
boundary restrictions; verify them in the validator instead of assuming every
internal type is accepted there.

`deserialize_json` requires a JSON object and each requested key. A `content`
output preserves an existing string and serializes a non-string JSON value;
it does not create an arbitrary object-typed wire. For typed structs use
`json_to_struct`, `struct_get` and `struct_to_json`. Serialize plain text once.
Never strip backslashes globally or recursively parse model text that resembles
JSON. Preserve booleans/null and nested objects at persistence boundaries.

The current terminal reader is `read_terminal_queue`, with `list-out`. Its
implementation reads queued input and returns a terminal-message wait when the
queue is empty. Do not design the older wait-then-read-history pattern. Terminal
and subprocess nodes in the general catalog are unavailable to main evolution
when the evolution policy excludes them.

## Experimental main evolution and installed capabilities

For this iterator, `agent_runtime/workflow_evolution.py` is an additional capability gate.
Preserve root ports, model IDs, tool declarations, and the full data dependency
chain of existing `workspace.get_file` readers. The catalog's `main_policy` marks
which runtime types this gate permits; existence in the catalog grants no access.
The design LLM returns a complete main JSON document with tools disabled. Choose
an unchanged document when there is no evidence for a useful structural change.

`metadata.tools` declares expected interfaces; it does not register Python
handlers. The deployed tool registry must contain `workspace.prepare_main_update`
before main evolution can run. Source code containing that function does not mean
an already running scheduler has loaded it. A missing tool is an infrastructure
failure, not evidence that a candidate was rejected or that no learning was needed.

Workspace write access compares process `runtime.write >= file.required.write`.
Uploading flow content, applying ACL, and loading runtime tools are separate
operations. Flow JSON does not carry the workspace file ACL. In this experiment,
commit the experience summary before attempting main evolution, so an evolution
exception does not discard the independently saved experience. Accepted main
writes still need validation, a checkpoint and revision-checked update.

## Complete examples checked by the actual validator and compiler

Echo a content input without model or tool dependencies:

```json
{
  "schema_version": "2.0",
  "metadata": {"structs": [], "tools": [], "functions": []},
  "input_ports": [{"name": "value", "type": "content"}],
  "output_ports": [{"name": "value", "type": "content"}],
  "nodes": [
    {"id": "in", "type": "input", "arguments": {}, "workflowPorts": [{"id": "workflow:value", "name": "value", "type": "content"}]},
    {"id": "out", "type": "output", "arguments": {}, "workflowPorts": [{"id": "workflow:value", "name": "value", "type": "content"}]}
  ],
  "connections": [
    {"fromId": "in", "fromPortId": "control-out", "toId": "out", "toPortId": "control-in", "type": "control"},
    {"fromId": "in", "fromPortId": "workflow:value", "toId": "out", "toPortId": "workflow:value", "type": "content"}
  ]
}
```

Extract an `observation` value from an object encoded as JSON text. A nested
observation object becomes JSON text on `value`, not a new object wire type:

```json
{
  "schema_version": "2.0",
  "metadata": {"structs": [], "tools": [], "functions": []},
  "input_ports": [{"name": "record", "type": "content"}],
  "output_ports": [{"name": "value", "type": "content"}],
  "nodes": [
    {"id": "in", "type": "input", "arguments": {}, "workflowPorts": [{"id": "workflow:record", "name": "record", "type": "content"}]},
    {"id": "extract", "type": "deserialize_json", "arguments": {"outputs": [{"key": "observation", "type": "content"}]}},
    {"id": "out", "type": "output", "arguments": {}, "workflowPorts": [{"id": "workflow:value", "name": "value", "type": "content"}]}
  ],
  "connections": [
    {"fromId": "in", "fromPortId": "control-out", "toId": "extract", "toPortId": "control-in", "type": "control"},
    {"fromId": "extract", "fromPortId": "control-out", "toId": "out", "toPortId": "control-in", "type": "control"},
    {"fromId": "in", "fromPortId": "workflow:record", "toId": "extract", "toPortId": "content-in", "type": "content"},
    {"fromId": "extract", "fromPortId": "observation", "toId": "out", "toPortId": "workflow:value", "type": "content"}
  ]
}
```

Report validation, adoption, runtime success and improved task results separately.
Compilation does not establish provider availability or better ALFWorld behavior.


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

## 记录与权限修复补充

- 即使事件数组已经结构化，task/result/observation/workspace/iterator_result 仍若保存 JSON 字符串，也会多一层转义。实验版记录 v2 直接嵌套这些对象，把状态与 checkpoint 收入 summary；普通 action/reasoning 字符串只编码一次。
- 只有确定来源为合法 JSON 的环境信封和运行时序列化结果可作为 JSON 片段嵌入；环境对象先解析验证。模型输出、引号、换行和 Windows 路径不做全局反转义，不递归猜测字符串内容。
- 权限分为进程 runtime 与目标文件 required；写入条件是 runtime.write >= required.write。本实验 iterator=3、main required.write=3，受保护参考文档/stable/bootstrap/iterator=4。生成时交叉校验，测试必须实际走工作区 API 写入，而不只比较清单数字。
- 更新 .flow 内容不会同步工作区 ACL，也不会修改已运行进程的权限快照。线上回退状态必须保留，不能用本地生成操作暗中重新发布。

## 以实现为准的参考资料

- 仓库旧 workflow-json skill 中的 wait_terminal_event/read_terminal_input 已不属于当前节点集合；当前终端节点为 read_terminal_queue。不要同时注入新声明和整份旧 skill，让模型自行消解冲突。
- 实验使用 workflow-json-runtime/SKILL.md，节点目录、端口和约束直接由当前代码导出；完整示例必须经过 validate_workflow 和 parse_workflow。参考文档同时保留编译、循环/函数生命周期、关键运行语义及 main 能力校验的原始代码摘录和源文件指纹。
- 代码中存在工具实现、metadata.tools 声明与运行进程已加载工具是三件不同的事。必须检查实际注册表，不能把“未知工具”解释成候选无改动。
- 先总结并保存经验，再尝试 main 迭代。缺工具、候选模型异常、checkpoint 或主文件写入失败不应抹掉已独立提交的经验；仍应显式记录 main 迭代失败。

## 工具契约与运行时验证补充

- 工具名出现在 metadata.tools 只说明工作流声明了接口；本地分发仍必须在 tools.tool.tool_handlers 中找到可调用的函数。旧 Python 进程不会因为绑定挂载的源码更新而重新执行 @tool。缺少 handler 会在 HTTP 请求前抛出“未知工具”。
- 参考文档的 workspace 工具 inputSchema/outputSchema 直接从 agent_runtime/tools/workspace.py 的 @tool 装饰器抽取；生成器不导入有 Redis 注册副作用的模块。契约测试另行加载真实装饰器，逐一比对抽取结果、实际注册值、迭代器端口。
- 候选校验结果 ready/unchanged/rejected 都是正常的具名输出；404/403 和 handler 缺失会抛异常，不能解释成“无需迭代”。revision 从文件读取结果以 number 传递，实际 API 值是整数；不经过 content 字符串转换。
- 模拟模型的全流程测试可能替代工具执行器；它能验证流程顺序与写入，但不能证明注册包装函数可调用。另用 test_runtime_tools.py 检查真实注册、统一 tool 节点分发、HTTP 包装、权限身份头、URL 编码、校验和结果传递。
- verify_runtime_tools.py 用临时只读工作流在线校验三个结果分支，使用线上 iterator 的接口和读取等级；可选 --include-recovery 以 bootstrap 的读取等级验证当前内容/稳定锚点恢复计划。后者使用 checkpoint_seq=0，不证明历史 checkpoint 回溯。探针不调用模型、不采纳候选、不修改 main/经验，完成后删除自身文件。


## Source fingerprints


- `agent_runtime/workflow_2_0.schema.json`: `980e150af00b929ba52b9f24fc54939202c13911ef2b0056f90c0820e7a139e0`

- `agent_runtime/workflow_contract.py`: `e1dc2cb70258d93c35d5aecf6aa64190b24aba1c1db5a43e1761591c06afffe8`

- `agent_runtime/workflow_validator.py`: `3d65dce379e5265377917a65fdbfbd143472a32de722fff26bda088029d49a74`

- `agent_runtime/workflow_functions.py`: `caaa24e2f7ac351cc03ba15a0aa4250bd16bafe7708318014992542388576ae6`

- `agent_runtime/workflow_parser.py`: `bd3c938f285b7e30c3e741507c7e087cbbc833449413693d9d3080c1b865f4eb`

- `agent_runtime/workflow_nodes.py`: `733fec5ad3887ab743114cc39199612bee7ad086bbbc66b9229452b19c463800`

- `agent_runtime/tools/tool.py`: `5b4aa5b6adefdbaf65abb6f6daf5feeeee94f3a0a864d31beb43fe7b46d5d62c`

- `agent_runtime/tools/workspace.py`: `ced4f86d4462ae8c59ea407dfe2e186db4e23d9af7eb4373e3bef263c27d12bb`

- `agent_runtime/workflow_recovery.py`: `e1ab5cc9768a573f9405053c174b4b4248ec4bcdd36e6339c9f67434b00045a2`

- `agent_runtime/workflow_evolution.py`: `ef8caad6f78d9d963f1e899ecf280a3233792e0334ef7655eb9415fdc4534b8f`

- `agent_runtime/workflow_tools.py`: `11784cfae7e315899ced6c266de5c9710ac6293d743e1e45c8010a1f8654dc87`

- `experiments/alfworld-recovery-scope/workflow-json-runtime/SKILL.md`: `400535500a17f7c70edbd52acfc210810fa6f9cd3108902e63cc0e37d9923e4c`

- Node types: 40. Regenerate with `python experiments/alfworld-recovery-scope/build_workflow_reference.py`.
