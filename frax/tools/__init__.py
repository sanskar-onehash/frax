def register_all_tools():
    from frax.tools import app_tools, capabilities, core, customizations

    core.register()
    capabilities.register()
    app_tools.register()
    customizations.register()
