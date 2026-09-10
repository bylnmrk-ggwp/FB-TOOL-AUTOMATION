"""
Main application entry point for Facebook Automation Tool.
"""
import sys
import traceback
from src.ui.main_window import MainWindow
from src.core.driver_manager import DriverManager


def run():
    """Launch the Facebook Automation GUI application."""
    try:
        # Create the driver manager first
        manager = DriverManager()
        
        # Create the main window and pass the manager
        app = MainWindow(driver_manager=manager)
        
        # Set the log callback to the log tab
        manager.log = app.log_tab.write
        
        # Start the driver manager background thread
        manager.start()
        
        # Test log message to verify connection
        app.log_tab.write("✓ FB Tool Automation started successfully")
        app.log_tab.write("✓ Driver manager initialized and ready")
        
        # Start the tkinter event loop
        app.mainloop()
        
        # Cleanup when app closes
        manager.stop()
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc()
        input("Press Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    run()
