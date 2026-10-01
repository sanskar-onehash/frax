def register_all_tools():
    from frax.tools import app_tools, capabilities, context, core, customizations, scripting

    core.register()
    context.register()
    capabilities.register()
    app_tools.register()
    customizations.register()
    scripting.register()
