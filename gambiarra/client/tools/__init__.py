# Client-side tool implementations for Gambiarra

from .file_ops import (
    ReadFileTool,
    WriteToFileTool,
    SearchFilesTool,
    ListFilesTool,
    InsertContentTool,
    SearchAndReplaceTool
)

from .command_ops import (
    ExecuteCommandTool,
    GitOperationTool
)

from .completion_ops import (
    AttemptCompletionTool,
    AskFollowupQuestionTool,
    NewTaskTool,
    ReportBugTool
)

from .diff_ops import (
    ApplyDiffTool,
    MultiApplyDiffTool,
    EditFileTool
)

from .search_ops import (
    CodebaseSearchTool,
    UpdateTodoListTool
)

from .base import (
    BaseTool,
    ToolResult,
    ToolManager,
    FileOperationTool,
    CommandExecutionTool
)

# All available tools
ALL_TOOLS = [
    # File operations
    ReadFileTool,
    WriteToFileTool,
    SearchFilesTool,
    ListFilesTool,
    InsertContentTool,
    SearchAndReplaceTool,

    # Command operations
    ExecuteCommandTool,
    GitOperationTool,

    # Completion and workflow
    AttemptCompletionTool,
    AskFollowupQuestionTool,
    NewTaskTool,
    ReportBugTool,

    # Diff and editing
    ApplyDiffTool,
    MultiApplyDiffTool,
    EditFileTool,

    # Search and analysis
    CodebaseSearchTool,
    UpdateTodoListTool,
]

# Tool registry for quick lookup
TOOL_REGISTRY = {tool.name: tool for tool in ALL_TOOLS}

__all__ = [
    'ALL_TOOLS',
    'TOOL_REGISTRY',
    'BaseTool',
    'ToolResult',
    'ToolManager',
    'FileOperationTool',
    'CommandExecutionTool',
    # File operations
    'ReadFileTool',
    'WriteToFileTool',
    'SearchFilesTool',
    'ListFilesTool',
    'InsertContentTool',
    'SearchAndReplaceTool',
    # Command operations
    'ExecuteCommandTool',
    'GitOperationTool',
    # Completion and workflow
    'AttemptCompletionTool',
    'AskFollowupQuestionTool',
    'NewTaskTool',
    'ReportBugTool',
    # Diff and editing
    'ApplyDiffTool',
    'MultiApplyDiffTool',
    'EditFileTool',
    # Search and analysis
    'CodebaseSearchTool',
    'UpdateTodoListTool',
]