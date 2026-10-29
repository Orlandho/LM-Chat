# -*- coding: utf-8 -*-
"""
Script to generate diagrams for LM-Chat technical documentation.
Renders Mermaid (.mmd) into SVG and PNG previews using mmdc and puppeteer.
Also creates corresponding editable .drawio XML files.
"""

import os
import json
import subprocess

PUPPETEER_CFG = os.path.abspath("scripts/puppeteer-config.json")
DIAG_DIR = os.path.abspath("docs/diagrams")
SRC_DIR = os.path.join(DIAG_DIR, "src")
SVG_DIR = os.path.join(DIAG_DIR, "svg")
PNG_DIR = os.path.join(DIAG_DIR, "png")

os.makedirs(SRC_DIR, exist_ok=True)
os.makedirs(SVG_DIR, exist_ok=True)
os.makedirs(PNG_DIR, exist_ok=True)

DIAGRAMS = {
    "01_system_context": {
        "title": "LM-Chat: Contexto del Sistema y Limites de Confianza",
        "mmd": """graph TD
    classDef omniHost fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef lmExt fill:#1e293b,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef mcpProc fill:#1c1917,stroke:#f59e0b,stroke-width:2px,color:#f8fafc;
    classDef localLLM fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#f8fafc;
    classDef cloudLLM fill:#312e81,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef storage fill:#3b0764,stroke:#ec4899,stroke-width:2px,color:#f8fafc;

    subgraph OMNIVERSE_HOST ["Proceso Host: NVIDIA Omniverse Kit SDK 105/106/107+"]
        RENDER_THREAD["Hilo de Renderizado Principal (Sacred 60 FPS RTX)"]:::omniHost
        STAGE[("OpenUSD Stage Activo: Prims, Xforms, Lights, Physics")]:::omniHost
        KIT_CMD["omni.kit.commands: Undo/Redo Stack (Ctrl+Z / Ctrl+Y)"]:::omniHost
        KIT_UNDO["omni.kit.undo (Begin/End Compound Blocks)"]:::omniHost
        
        subgraph LM_CHAT_EXT ["Extension LM-Chat (orlandodorival.lm_chat)"]
            GUI["ChatWindow GUI (omni.ui)"]:::lmExt
            CLI["LM-Chat CLI Harness (cli/lmchat_cli.py)"]:::lmExt
            AGENT_MGR["AgentManager (Bucle ReAct 3 intentos totales)"]:::lmExt
            ROUTER["InferenceRouter (SSE Streaming & Heuristica)"]:::lmExt
            USD_CTRL["USDController & AST Sandbox"]:::lmExt
            USD_INSP["USDInspector (audit, find, layer stack)"]:::lmExt
            DIAG_ENG["DiagnosticsEngine & Structured Logger"]:::lmExt
        end

        RENDER_THREAD -.->|"Async Tasks (No Bloqueante)"| AGENT_MGR
        USD_CTRL -->|"Ejecucion con Undo"| KIT_CMD
        KIT_CMD -->|"Mutacion Segura"| STAGE
        USD_CTRL -->|"Agrupamiento de Historial"| KIT_UNDO
        USD_INSP -->|"Inspeccion Solo Lectura"| STAGE
    end

    subgraph MCP_SUBPROCESSES ["Subprocesos Locales MCP (Aislamiento stdio)"]
        MCP_REG["OmniMCPRegistry (mcp/omni_mcp_registry.py)"]:::mcpProc
        MCP_CONN["MCPServerConnection (Subprocess stdio / JSON-RPC 2.0)"]:::mcpProc
        SERVER_FS["MCP Server: FileSystem / Specs"]:::mcpProc
        SERVER_DOCS["MCP Server: Omniverse Docs / CAD"]:::mcpProc
        
        MCP_REG --> MCP_CONN
        MCP_CONN -->|"stdin / stdout"| SERVER_FS
        MCP_CONN -->|"stdin / stdout"| SERVER_DOCS
    end

    subgraph LOCAL_INFERENCE ["Servidores de Inferencia Locales (Air-Gapped)"]
        LM_STUDIO["LM Studio Server (:1234): Integrations REST & VRAM Manager"]:::localLLM
        OLLAMA["Ollama Server (:11434): DeepSeek-R1, Qwen 2.5 Coder"]:::localLLM
        VLLM_CLUSTER["vLLM / Local Cluster (:8000): ClusterManager"]:::localLLM
    end

    subgraph CLOUD_INFERENCE ["Proveedores Cloud Frontier (HTTPS / TLS 1.3)"]
        GEMINI["Google Gemini API: gemini-3.8-flash, gemini-3.7-flash"]:::cloudLLM
        CLAUDE["Anthropic Claude API: claude-3-7-sonnet, opus-5.5"]:::cloudLLM
        OPENAI["OpenAI API: o3-mini, gpt-4o, gpt-6"]:::cloudLLM
        NVIDIA_NIM["NVIDIA NIM / Spark: Nemotron 70B, Cosmos 3"]:::cloudLLM
    end

    subgraph SECURE_STORAGE ["Almacenamiento Local Seguro (~/.omni_lm_chat/)"]
        SESSIONS[("Directorio de Sesiones JSON: Permisos 0o600 / 0o700")]:::storage
        SETTINGS_CONF["Configuracion Persistente: settings.json"]:::storage
        LOG_FILES[("Archivos de Registro: Rotating Log Files")]:::storage
    end

    GUI --> AGENT_MGR
    CLI --> AGENT_MGR
    AGENT_MGR --> ROUTER
    AGENT_MGR --> USD_CTRL
    USD_CTRL --> USD_INSP
    AGENT_MGR <-->|"Herramientas / Tool Calls"| MCP_REG

    ROUTER <-->|"HTTP / SSE Streaming"| LOCAL_INFERENCE
    ROUTER <-->|"HTTPS / SSE Streaming"| CLOUD_INFERENCE

    AGENT_MGR <-->|"Persistencia de Sesiones"| SESSIONS
    LM_CHAT_EXT <-->|"Lectura / Escritura"| SETTINGS_CONF
    DIAG_ENG -->|"Persistencia de Logs"| LOG_FILES
"""
    },
    "02_component_architecture": {
        "title": "LM-Chat: Arquitectura de Componentes, Interfaces y Dependencias",
        "mmd": """graph TD
    classDef iface fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#38bdf8,stroke-dasharray: 5 5;
    classDef uiLayer fill:#1e293b,stroke:#0284c7,stroke-width:2px,color:#f8fafc;
    classDef logicLayer fill:#1e1e2e,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef coreLayer fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#f8fafc;
    classDef mcpLayer fill:#1c1917,stroke:#f59e0b,stroke-width:2px,color:#f8fafc;
    classDef storeLayer fill:#3b0764,stroke:#ec4899,stroke-width:2px,color:#f8fafc;

    subgraph UI_LAYER ["Capa de Presentacion (ui/)"]
        CW["ChatWindow (omni.ui.Window)"]:::uiLayer
        CD["ChatDelegate (Model-Delegate-View)"]:::uiLayer
        SW["SettingsWindow (Modal Settings)"]:::uiLayer
        CF["CollapsibleFrame (omni.ui)"]:::uiLayer
        PC["PlanCard (UI Widget con [Ejecutar] y [Cancelar])"]:::uiLayer
    end

    subgraph INTERFACES ["Contratos Tipados (core/interfaces.py)"]
        I_ROUTER["IInferenceRouter"]:::iface
        I_USD_CTRL["IUSDController"]:::iface
        I_USD_INSP["IUSDInspector"]:::iface
        I_POLICY["IAgentPolicy"]:::iface
        I_MCP["IMCPClientRegistry"]:::iface
        I_HISTORY["IChatHistoryManager"]:::iface
        I_SETTINGS["ISettingsManager"]:::iface
        I_CLUSTER["IClusterManager"]:::iface
        I_VRAM["ILMStudioVRAMManager"]:::iface
    end

    subgraph LOGIC_LAYER ["Capa de Negocio y Cognicion (logic/)"]
        AM["AgentManager (Bucle ReAct 3 intentos totales)"]:::logicLayer
        IR["InferenceRouter (Multi-Provider Gateway)"]:::logicLayer
        SRP["StreamingReasoningParser (<think> Tag Parser)"]:::logicLayer
        UC["USDController (Sandbox con __builtins__ y Undo)"]:::logicLayer
        UI_INSP["USDInspector (Auditoria de Assets y Layer Stack)"]:::logicLayer
        SP["SpatialSecurityPolicy (core/policies.py AST)"]:::logicLayer
        CH["LocalChatHistoryManager (Persistencia Atomica JSON)"]:::logicLayer
        SM["SettingsManager (~/.omni_lm_chat/settings.json)"]:::logicLayer
        CM["ClusterManager (Failover y Balanceo)"]:::logicLayer
        VM["LMStudioVRAMManager (Descarga VRAM)"]:::logicLayer
        DE["DiagnosticsEngine & Logger"]:::logicLayer
    end

    subgraph MCP_LAYER ["Subsistema de Herramientas MCP (mcp/)"]
        OMCP["OmniMCPRegistry (Registro Dinamico)"]:::mcpLayer
        MSC["MCPServerConnection (Subprocess stdio)"]:::mcpLayer
    end

    CW --> CD
    CW --> CF
    CW --> PC
    CW -.-> SW
    
    CD --> AM
    SW --> SM
    SW --> VM
    SW --> CM

    AM -.-> I_ROUTER
    IR -.-> I_ROUTER
    UC -.-> I_USD_CTRL
    UI_INSP -.-> I_USD_INSP
    SP -.-> I_POLICY
    OMCP -.-> I_MCP
    CH -.-> I_HISTORY
    SM -.-> I_SETTINGS
    CM -.-> I_CLUSTER
    VM -.-> I_VRAM

    AM --> IR
    AM --> UC
    AM --> OMCP
    AM --> CH
    AM --> DE
    IR --> SRP
    IR --> CM
    UC --> SP
    UC --> UI_INSP
    OMCP --> MSC
"""
    },
    "03_conversational_flow": {
        "title": "LM-Chat: Flujo Conversacional GUI/CLI y Bifurcacion de Modos",
        "mmd": """sequenceDiagram
    autonumber
    actor U as Usuario (GUI / CLI)
    participant CW as ChatWindow / CLI
    participant AM as AgentManager
    participant IR as InferenceRouter
    participant LLM as Motor LLM
    participant UC as USDController
    participant SP as SpatialSecurityPolicy (AST)
    participant STAGE as OpenUSD Stage

    U->>CW: Ingresa Prompt ("Crea 3 cilindros y cambia el material")
    CW->>AM: process_prompt(prompt, callbacks...)
    activate AM
    AM->>AM: Registra mensaje en memoria conversacional
    AM->>IR: stream_chat_completions(messages, tools, integrations)
    activate IR
    IR->>LLM: Peticion HTTP SSE Streaming (timeout=600s)
    activate LLM

    loop Streaming de Tokens
        LLM-->>IR: Chunk SSE (delta: content / reasoning / tool_calls)
        alt Tokens de Razonamiento (<think> o reasoning_content)
            IR-->>CW: reasoning_callback(chunk)
            CW->>CW: Renderiza en CollapsibleFrame
        else Tokens de Contenido Final
            IR-->>CW: append_callback(chunk)
            CW->>CW: Fusiona tokens en burbuja activa
        end
    end
    deactivate LLM
    deactivate IR

    AM->>AM: Limpia etiquetas <think> y busca bloque python

    alt No contiene bloque de codigo Python
        AM-->>CW: Retorna texto de respuesta
        CW-->>U: Muestra respuesta conversacional completa
    else Contiene bloque de codigo Python
        alt MODO PLAN_AND_CONFIRM (Plan y Revision)
            AM->>AM: Retiene codigo en _pending_code (NO ejecuta)
            AM-->>CW: confirmation_callback(code, plan_details)
            CW->>CW: Muestra PlanCard interactiva con preview
            CW-->>U: Presenta botones [Ejecutar en Stage] y [Cancelar]

            alt Usuario pulsa [Cancelar]
                U->>CW: Click [Cancelar]
                CW->>AM: cancel_pending_code()
                AM->>AM: Descarta _pending_code
                AM-->>CW: Confirmacion de cancelacion
                CW-->>U: Notifica: "Propuesta descartada. Escena intacta."
            else Usuario pulsa [Ejecutar en Stage]
                U->>CW: Click [Ejecutar en Stage]
                CW->>AM: execute_pending_code()
                activate AM
                AM->>UC: execute_code(pending_code)
                activate UC
                UC->>SP: validate_code(code)
                alt Violacion de Politica de Seguridad (AST)
                    SP-->>UC: (False, "Violation: module forbidden")
                    UC-->>AM: {success: False, error_msg: "..."}
                    AM-->>CW: Muestra error de seguridad
                else Codigo Valido
                    SP-->>UC: (True, None)
                    UC->>STAGE: omni.kit.undo.begin() -> exec() -> omni.kit.undo.end()
                    STAGE-->>UC: Mutacion completada
                    UC-->>AM: {success: True}
                    AM-->>CW: Notifica: "Codigo ejecutado exitosamente"
                    CW-->>U: Actualiza vista 3D en Omniverse
                end
                deactivate UC
                deactivate AM
            end

        else MODO IMMEDIATE (Fast Act / Ejecucion Directa)
            AM->>UC: execute_code(extracted_code)
            activate UC
            UC->>SP: validate_code(code)
            alt Validacion Exitosa y Ejecucion en Stage
                SP-->>UC: (True, None)
                UC->>STAGE: omni.kit.undo.begin() -> exec() -> omni.kit.undo.end()
                UC-->>AM: {success: True}
                AM-->>CW: Notifica exito
                CW-->>U: Escena actualizada inmediatamente
            else Error en Ejecucion (Sdf.PathError / Runtime)
                UC-->>AM: {success: False, error_msg: "..."}
                deactivate UC
                Note over AM,LLM: Bucle ReAct de Autocorreccion (Hasta 3 intentos totales)
                AM->>IR: Reconsulta con traceback de error
                IR->>LLM: Prompt de reflexion de error...
            end
        end
    end
    deactivate AM
"""
    },
    "04_inference_streaming_tools": {
        "title": "LM-Chat: Ciclo de Inferencia, Streaming SSE, Razonamiento y Herramientas MCP",
        "mmd": """flowchart TD
    classDef startNode fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef checkNode fill:#1e1e2e,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef actionNode fill:#1e293b,stroke:#0284c7,stroke-width:2px,color:#f8fafc;
    classDef mcpNode fill:#1c1917,stroke:#f59e0b,stroke-width:2px,color:#f8fafc;
    classDef errorNode fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#f8fafc;

    START([Inicio: Mensaje de Usuario en Cola]):::startNode --> DETECT[InferenceRouter: Analisis de Modelo Activo]:::actionNode
    
    DETECT --> REASON_CHECK{is_reasoning_model: Regex Check}:::checkNode
    
    REASON_CHECK -- Si: o1, o3, DeepSeek-R1, Claude Thinking --> ADAPT_REASON[Adaptar Payload: Omitir temperature y fijar max_completion_tokens]:::actionNode
    REASON_CHECK -- No: Modelo Estandar --> ADAPT_STD[Configurar temperature y max_tokens]:::actionNode

    ADAPT_REASON --> TOOL_CHECK{Existen Herramientas MCP Registradas?}:::checkNode
    ADAPT_STD --> TOOL_CHECK

    TOOL_CHECK -- Si --> FORMAT_TOOLS[Construir Payload tools e Integrations para LM Studio]:::mcpNode
    TOOL_CHECK -- No --> DISPATCH_HTTP[Despachar Peticion HTTP SSE Streaming]:::actionNode

    FORMAT_TOOLS --> DISPATCH_HTTP

    DISPATCH_HTTP --> SSE_STREAM{Recibiendo Chunks SSE?}:::checkNode

    SSE_STREAM -- Chunk Exitoso --> PARSE_CHUNK[StreamingReasoningParser / Delta Parser]:::actionNode

    PARSE_CHUNK --> CHUNK_TYPE{Tipo de Chunk?}:::checkNode

    CHUNK_TYPE -- Reasoning / think --> STREAM_THINK[reasoning_callback: Canalizar a CollapsibleFrame en UI]:::actionNode
    CHUNK_TYPE -- Contenido Markdown --> STREAM_CONTENT[append_callback: Fusionar tokens en burbuja activa]:::actionNode
    CHUNK_TYPE -- Tool Call Delta --> ACCUM_TOOL[Acumular fragmentos de funcion y argumentos JSON]:::mcpNode

    STREAM_THINK --> SSE_STREAM
    STREAM_CONTENT --> SSE_STREAM
    ACCUM_TOOL --> SSE_STREAM

    SSE_STREAM -- Fin de Stream --> EVAL_TOOLS{Se acumularon tool_calls?}:::checkNode

    EVAL_TOOLS -- Si --> CALL_MCP[OmniMCPRegistry.call_tool: Despacho JSON-RPC 2.0 a Subproceso]:::mcpNode
    CALL_MCP --> INJECT_TOOL_RES[Inyectar mensaje role: tool con resultado JSON]:::mcpNode
    INJECT_TOOL_RES --> DISPATCH_HTTP

    EVAL_TOOLS -- No --> EXTRACT_CODE[AgentManager: Extraer Python Code ignorando think]:::actionNode

    SSE_STREAM -- Error HTTP / Timeout --> DIAGNOSE[DiagnosticsEngine: diagnose_inference_failure]:::errorNode
    DIAGNOSE --> RENDER_DIAG_CARD[Renderizar Tarjeta Markdown de Diagnostico con Solucion]:::errorNode
"""
    },
    "05_usd_execution_and_error_recovery": {
        "title": "LM-Chat: Pipeline de Ejecucion OpenUSD, Gobernanza AST y Recuperacion ReAct",
        "mmd": """flowchart TD
    classDef startNode fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef checkNode fill:#1e1e2e,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef actionNode fill:#1e293b,stroke:#0284c7,stroke-width:2px,color:#f8fafc;
    classDef secureNode fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#f8fafc;
    classDef errorNode fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#f8fafc;

    CODE_IN([Bloque de Codigo Python Extraido]):::startNode --> VALID_SIZE{Longitud <= 100,000 bytes?}:::checkNode

    VALID_SIZE -- No --> REJECT_SIZE[Error de Seguridad: Tamano Excedido]:::errorNode
    VALID_SIZE -- Si --> AST_PARSE[Analisis Sintactico: ast.parse]:::actionNode

    AST_PARSE -- Error de Sintaxis --> SYNTAX_ERR[Fallo de Sintaxis en Codigo Generado]:::errorNode
    AST_PARSE -- Arbol Valido --> AST_WALK[Inspeccion de Nodos AST: SpatialSecurityPolicy]:::secureNode

    AST_WALK --> CHECK_MODULES{Importa Modulos Prohibidos: shutil, subprocess, socket, winreg?}:::checkNode
    CHECK_MODULES -- Si --> VIOLATION[Rechazo Preventivo: Modulo Prohibido]:::errorNode

    CHECK_MODULES -- No --> CHECK_BUILTINS{Llama a Builtins Peligrosos: eval, exec, os.system?}:::checkNode
    CHECK_BUILTINS -- Si --> VIOLATION

    CHECK_BUILTINS -- No --> CHECK_LOOPS{Bucle Infinito: while True sin break o range > 10,000?}:::checkNode
    CHECK_LOOPS -- Si --> VIOLATION

    CHECK_LOOPS -- No --> CHECK_PRIMS{Manipula Prims Protegidos: /OmniverseKit_Root, /Render?}:::checkNode
    CHECK_PRIMS -- Si --> VIOLATION

    CHECK_PRIMS -- No --> PREP_SANDBOX[Preparar Entorno Seguro: __builtins__ explicito, omni, pxr, inspector, controller]:::secureNode

    PREP_SANDBOX --> OPEN_UNDO[omni.kit.undo.begin: Abrir Bloque Compuesto]:::actionNode

    OPEN_UNDO --> EXEC_PY[exec python_code in exec_globals]:::actionNode

    EXEC_PY --> EXEC_RESULT{Ejecucion Exitosa?}:::checkNode

    EXEC_RESULT -- Si --> CLOSE_UNDO_OK[omni.kit.undo.end: Cerrar Bloque Undo con Exito]:::secureNode
    CLOSE_UNDO_OK --> SUCCESS_NOTIFY([Notificacion al Usuario: Cambios Aplicados en Stage]):::startNode

    EXEC_RESULT -- Excepcion (Sdf.PathError, Tf.Diagnostic) --> CLOSE_UNDO_ERR[omni.kit.undo.end: Cerrar Bloque Undo y Capturar Traceback]:::errorNode

    CLOSE_UNDO_ERR --> RETRY_CHECK{"Intento &lt; 2? (Total: 3 Intentos Maximo)"}:::checkNode

    RETRY_CHECK -- Si: Intento 1 o 2 --> REACT_REFLECT[Bucle ReAct: Inyectar Traceback y Prompt de Reflexion]:::actionNode
    REACT_REFLECT --> REQUERY_LLM[Re-consultar Modelo LLM para Autocorreccion]:::actionNode
    REQUERY_LLM --> CODE_IN

    RETRY_CHECK -- No: Reintentos Agotados --> FINAL_DIAG[DiagnosticsEngine: Diagnostico Final Enriquecido y Registro]:::errorNode
    FINAL_DIAG --> FAIL_NOTIFY([Notificar Agotamiento de Reintentos en UI]):::errorNode
"""
    },
    "06_persistence_session_lifecycle": {
        "title": "LM-Chat: Ciclo de Vida de Sesiones, Persistencia Atomica y Configuracion",
        "mmd": """flowchart TD
    classDef startNode fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef actionNode fill:#1e293b,stroke:#0284c7,stroke-width:2px,color:#f8fafc;
    classDef checkNode fill:#1e1e2e,stroke:#a855f7,stroke-width:2px,color:#f8fafc;
    classDef storageNode fill:#3b0764,stroke:#ec4899,stroke-width:2px,color:#f8fafc;
    classDef secureNode fill:#14532d,stroke:#22c55e,stroke-width:2px,color:#f8fafc;

    INIT([Arranque de Extension / CLI]):::startNode --> LOAD_CONF[SettingsManager: Cargar ~/.omni_lm_chat/settings.json]:::actionNode

    LOAD_CONF --> CONF_EXISTS{settings.json Existe?}:::checkNode
    CONF_EXISTS -- No --> CREATE_DEFAULTS[Inicializar Valores Predeterminados: LM Studio :1234, Gemini 3.8, Ollama :11434]:::actionNode
    CONF_EXISTS -- Si --> PARSE_CONF[Cargar Proveedor, Modelo, URL, Keys y MCP Servers]:::actionNode
    CREATE_DEFAULTS --> PARSE_CONF

    PARSE_CONF --> INIT_HIST[LocalChatHistoryManager: Inicializar Directorio de Sesiones]:::actionNode

    INIT_HIST --> LIST_SESS[list_sessions: Escaneo de ~/.omni_lm_chat/sessions/]:::storageNode

    LIST_SESS --> HAS_SESS{Existen Sesiones Previas?}:::checkNode

    HAS_SESS -- Si --> RESTORE_LATEST[Recuperar Ultima Sesion Activa por updated_at]:::actionNode
    HAS_SESS -- No --> CREATE_NEW[create_session: Generar Nueva Sesion UUIDv4 en UTC ISO 8601]:::actionNode

    RESTORE_LATEST --> SYNC_AGENT[AgentManager.load_session_messages: Sincronizar Historial Reteniendo System Prompt]:::actionNode
    CREATE_NEW --> SYNC_AGENT

    SYNC_AGENT --> USER_TURN([Interaccion Usuario / Asistente]):::startNode

    USER_TURN --> SAVE_REQ[save_session: Persistencia en Disco]:::actionNode

    SAVE_REQ --> SANITIZE_SID[Sanitizar session_id: Prevenir Directory Traversal]:::secureNode

    SANITIZE_SID --> ATOMIC_WRITE[Escritura Atomica Segura: Archivo .tmp, permisos 0o600 / 0o700, os.replace]:::secureNode

    ATOMIC_WRITE --> SEARCH_OP{Operacion de Busqueda?}:::checkNode

    SEARCH_OP -- Si --> SEARCH_PASS[search_sessions: Busqueda Monopasada por Titulo y Mensajes]:::actionNode
    SEARCH_PASS --> RENDER_SEARCH[Actualizar Dropdown / Lista en UI y CLI]:::actionNode

    SEARCH_OP -- No --> EXPORT_OP{Exportar / Importar?}:::checkNode

    EXPORT_OP -- Exportar --> EXPORT_JSON[export_session_json: Generar Cadena JSON Estructurada]:::actionNode
    EXPORT_OP -- Importar --> IMPORT_JSON[import_session_json: Validar Esquema, Asignar Nuevo ID y Guardar]:::actionNode
"""
    }
}


def generate_drawio_xml(name: str, title: str, mmd_content: str) -> str:
    """Generates an editable .drawio XML file with mxGraphModel structure."""
    escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    escaped_mmd = mmd_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" modified="2026-10-28T23:30:00.000Z" agent="Antigravity-DocEngine" version="24.7.17" type="device">
  <diagram id="{name}" name="{escaped_title}">
    <mxGraphModel dx="1600" dy="1200" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1800" pageHeight="1400" background="#0b0f19" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        
        <!-- TITULO PRINCIPAL -->
        <mxCell id="title_node" value="&lt;b&gt;LM-Chat™ &amp;mdash; {escaped_title}&lt;/b&gt;&lt;br/&gt;&lt;font color='#94a3b8'&gt;NVIDIA Omniverse Kit Extension (orlandodorival.lm_chat) &amp;bull; Version 1.2.0&lt;/font&gt;" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=18;fontColor=#38bdf8;" vertex="1" parent="1">
          <mxGeometry x="50" y="20" width="1700" height="50" as="geometry" />
        </mxCell>

        <!-- CONTENEDOR PRINCIPAL DEL DIAGRAMA -->
        <mxCell id="canvas_box" value="" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#0f172a;strokeColor=#1e293b;strokeWidth=2;arcSize=6;" vertex="1" parent="1">
          <mxGeometry x="50" y="90" width="1700" height="1250" as="geometry" />
        </mxCell>

        <!-- FUENTE MERMAID / ESPECIFICACION ESTRUCTURADA -->
        <mxCell id="spec_node" value="&lt;h3 style='color:#38bdf8; margin:0 0 8px 0;'&gt;Especificacion de Arquitectura / Flujo Estructurado&lt;/h3&gt;&lt;pre style='color:#e2e8f0; font-family:Consolas, monospace; font-size:11px; white-space:pre-wrap;'&gt;{escaped_mmd}&lt;/pre&gt;" style="text;html=1;strokeColor=#334155;fillColor=#1e293b;align=left;verticalAlign=top;whiteSpace=wrap;rounded=1;spacing=16;overflow=hidden;" vertex="1" parent="canvas_box">
          <mxGeometry x="40" y="40" width="1620" height="1170" as="geometry" />
        </mxCell>

      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""
    return xml


def main():
    for name, data in DIAGRAMS.items():
        print(f"Generating diagram: {name}...")
        mmd_path = os.path.join(SRC_DIR, f"{name}.mmd")
        svg_path = os.path.join(SVG_DIR, f"{name}.svg")
        png_path = os.path.join(PNG_DIR, f"{name}.png")
        drawio_path = os.path.join(SRC_DIR, f"{name}.drawio")

        # 1. Write Mermaid Source
        with open(mmd_path, "w", encoding="utf-8") as f:
            f.write(data["mmd"].strip())

        # 2. Render SVG via mmdc
        cmd_svg = f'mmdc -p "{PUPPETEER_CFG}" -i "{mmd_path}" -o "{svg_path}" -b transparent'
        res_svg = subprocess.run(cmd_svg, shell=True, capture_output=True, text=True)
        if res_svg.returncode != 0:
            print(f"  [!] Error rendering SVG {name}: {res_svg.stderr}")
        else:
            print(f"  [+] SVG generated ({os.path.getsize(svg_path)} bytes)")

        # 3. Render PNG via mmdc
        cmd_png = f'mmdc -p "{PUPPETEER_CFG}" -i "{mmd_path}" -o "{png_path}" -b transparent'
        res_png = subprocess.run(cmd_png, shell=True, capture_output=True, text=True)
        if res_png.returncode != 0:
            print(f"  [!] Error rendering PNG {name}: {res_png.stderr}")
        else:
            print(f"  [+] PNG generated ({os.path.getsize(png_path)} bytes)")

        # 4. Generate Editable .drawio XML
        drawio_xml = generate_drawio_xml(name, data["title"], data["mmd"].strip())
        with open(drawio_path, "w", encoding="utf-8") as f:
            f.write(drawio_xml)
        print(f"  [+] Draw.io generated ({os.path.getsize(drawio_path)} bytes)")

    print("\nAll 6 architectural diagrams generated successfully.")


if __name__ == "__main__":
    main()
