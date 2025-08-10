import os
import streamlit as st

def setup_gurobi_license():
    """
    Sets up the Gurobi license from Streamlit secrets.
    This function should be called once at the start of the app.
    """
    # Check if running on Streamlit Cloud
    if "STREAMLIT_SERVER_PORT" in os.environ:
        # These secrets should be set in the Streamlit Cloud app settings
        gurobi_secrets = st.secrets.get("gurobi")
        if gurobi_secrets:
            os.environ["GRB_CLOUDACCESSID"] = gurobi_secrets.get("CLOUDACCESSID")
            os.environ["GRB_CLOUDKEY"] = gurobi_secrets.get("CLOUDKEY")
            os.environ["GRB_CSAPPNAME"] = gurobi_secrets.get("CSAPPNAME")
            print("Gurobi license set from Streamlit secrets.")
