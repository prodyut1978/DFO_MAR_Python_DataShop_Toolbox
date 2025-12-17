import glob
import matplotlib.pyplot as plt
from matplotlib.widgets import LassoSelector, Button, RadioButtons, CheckButtons
from matplotlib.path import Path
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle, Patch
import matplotlib.colors as mcolors
import numpy as np
import os
import shutil
from datetime import datetime
import pandas as pd
import pathlib
import sys
import time
from PyQt6.QtWidgets import (
    QApplication,QMessageBox)
from datashop_toolbox.thermograph import ThermographHeader
from datashop_toolbox.historyhdr import HistoryHeader
from datashop_toolbox.validated_base import get_current_date_time
from datashop_toolbox import select_metadata_file_and_data_folder
from datashop_toolbox.log_window import (
    SafeConsoleFilter, 
    SafeConsoleFilter, 
    LogWindowUI)
from collections import Counter
import logging

exit_requested = False
global logger
logger = logging.getLogger("datashop")
logger.setLevel(logging.INFO)
logger.propagate = False 
console_handler = logging.StreamHandler()
console_handler.addFilter(SafeConsoleFilter())
console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(console_handler)
file_handler = logging.FileHandler("datashop_log.txt", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(file_handler)
logger.info("Logger file initialized.")

FLAG_LABELS = {
            0: "Not been QC'd",
            1: "Correct",
            2: "Inconsistent",
            3: "Doubtful",
            4: "Erroneous",
            5: "Modified",
        }


FLAG_COLORS = {
            0: "#808080",
            1: "#02590F",
            2: "#B59410",
            3: "#8B008B",
            4: "#FF0000",
            5: "#00008B",
        }


def run_qc_thermograph_data(input_path, output_path, qc_operator):
    logger.info(f"Starting QC Thermograph Data task by {qc_operator} on {input_path}")
    wildcard = "*.ODF"
    task_completion= qc_thermograph_data(input_path, wildcard, output_path, qc_operator)
    if task_completion["finished"]:
        logger.info(f"QC Thermograph Data task completed successfully.")
    else:
        print("QC Thermograph Data task did not complete.")
    return task_completion
   

def prepare_output_folder(in_folder_path: str, out_folder_path: str, qc_operator: str) -> str:
    base_name_input = "Step_1_Create_ODF"
    in_folder_path = os.path.abspath(in_folder_path)
    
    base_name_output = "Step_2_Assign_QFlag"
    out_folder_path = os.path.abspath(out_folder_path)
    out_odf_path = os.path.join(out_folder_path, base_name_output)
    out_odf_path = os.path.abspath(out_odf_path)

    
    if base_name_input.lower() in in_folder_path.lower():
        if (not os.path.exists(out_odf_path)) and (out_odf_path != in_folder_path):
            logger.info(f"Initial QC Mode: No existing output folder found. Creating new folder, name : Step_2_Assign_QFlag")
            os.makedirs(out_odf_path, exist_ok=True)
            logger.info(f"Created output folder: {out_odf_path}")
        else:
            logger.info(f"Initial QC Mode: Overwriting existing output folder, name : Step_2_Assign_QFlag")
            shutil.rmtree(out_odf_path)
            os.makedirs(out_odf_path, exist_ok=True)
            logger.warning(f"Overwriting existing folder: {out_odf_path}")
    else:
        logger.info(f"Review QC Mode: Creating new reviewed output folder, name: Step_3_Review_QFlag_with timestamp.")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"Step_3_Review_QFlag_{qc_operator.strip().title()}_{timestamp}"
        out_odf_path = os.path.join(out_folder_path, new_name)
        os.makedirs(out_odf_path, exist_ok=True)
        logger.info(f"Created new reviewed output folder: {out_odf_path}")

    return out_odf_path


def qc_thermograph_data(in_folder_path: str, wildcard: str, out_folder_path: str, qc_operator: str):
    """
    Processes ODF files in `in_folder_path` matching `wildcard`, writes to out_folder_path/Step_2_Quality_Flagging.
    Uses global `exit_requested` to allow user interruption.
    Returns {"finished": bool}
    """
    
    global exit_requested
    exit_requested = False
    batch_result_container = {"finished": False}

    cwd = os.getcwd()

    try:
        os.chdir(in_folder_path)
        logger.info(f"Changed working dir to the input directory: {in_folder_path}")
    except Exception as e:
        logger.exception(f"Cannot change directory: {e}")
        return batch_result_container
    
    mtr_files = glob.glob(wildcard)
    if not mtr_files:
        logger.warning("No ODF files found in selected folder.")
        os.chdir(cwd)
        return batch_result_container


    # Prepare output folder
    out_odf_path = prepare_output_folder(in_folder_path, out_folder_path, qc_operator)
    logger.info(f"Created a output data folder name, Step_2_Quality_Flagging ")
    logger.info(f"Path for Step_2_Quality_Flagging: {out_odf_path}")

    os.chdir(cwd)

    for idx, mtr_file in enumerate(mtr_files, start=1):
        if exit_requested:
            logger.warning("Exit requested — stopping QC loop.")
            break
        
        logger.info(f"Reading file {idx} of {len(mtr_files)}: {mtr_file}")
        logger.info(f"Please wait...reading ODF file for QC visualization...")

        full_path = str(pathlib.Path(in_folder_path, mtr_file))
        
        try:
            mtr = ThermographHeader()
            mtr.read_odf(full_path)
        except Exception as e:
            logger.exception(f"Failed to read ODF {full_path}: {e}")
            continue

        orig_df = mtr.data.data_frame
        orig_df_stored = orig_df.copy()
        orig_df =orig_df.copy()
        orig_df.reset_index(drop=True, inplace=True)
        orig_df= pd.DataFrame(orig_df)

        # Extract temperature and time
        temp = orig_df['TE90_01'].to_numpy()
        sytm = orig_df['SYTM_01'].str.lower().str.strip("'")
        
        if 'QTE90_01' in orig_df.columns:
            qflag = orig_df['QTE90_01'].to_numpy().astype(int)
        else:
            orig_df['QTE90_01']= np.zeros(len(orig_df), dtype=int)
            qflag = orig_df['QTE90_01'].to_numpy().astype(int)
        
        try:
            dt = pd.to_datetime(sytm, format='%d-%b-%Y %H:%M:%S.%f')
        except Exception:
            dt = pd.to_datetime(sytm, infer_datetime_format=True, errors="coerce")

       
        # Create a DataFrame with Temperature as the variable and DateTime as the index.
        df = pd.DataFrame({'Temperature': temp, 'qualityflag': qflag}, index=dt)
        N = len(df)
        qc_mode_slection=np.sum(df['qualityflag'])
        if qc_mode_slection == 0:
            qc_mode_=" QC Mode - Initial\n(No Previous QC Flags)"
            qc_mode_code_=0
        else:
            qc_mode_=" QC Mode - Review\n(With Previous QC Flags)"
            qc_mode_code_=1
        logger.info(f"QC Mode for this file {mtr_file}: {qc_mode_}")

        # Convert datetime to numeric for lasso selection
        xnums = mdates.date2num(df.index.to_pydatetime())
        xy = np.column_stack([mdates.date2num(df.index.to_pydatetime()), df['Temperature']])
        colors_initial = [FLAG_COLORS.get(int(f), "#808080") for f in df['qualityflag']]

        # Store multiple selection groups
        selection_groups = []
        applied = False
        user_exited = False
        current_flag = 4
        figsize=(13, 6)
        
        plt.style.use('ggplot')
        fig = plt.figure(figsize=figsize)
        ax = fig.add_axes([0.065, 0.15, 0.72, 0.8])

        qcMode_ax = fig.add_axes([0.78, 0.78, 0.1, 0.35])
        qcMode_ax.set_axis_off()
        qcMode_ax.set_title("QC Mode:", fontsize=12, pad=0, 
                   fontweight='heavy', color='navy',
                   family='serif', loc='right')
        qcMode = CheckButtons(
                qcMode_ax,
                labels=[qc_mode_],
                actives=[False],
                )
        for label in qcMode.labels:
            label.set_fontsize(12)
            label.set_fontweight('bold')
            label.set_family('serif')
        
        radio_ax = fig.add_axes([0.80, 0.20, 0.2, 0.35])
        radio_ax.set_axis_off()
        radio_ax.set_title("Assign Quality Codes for\nSelected Points:", fontsize=12, pad=0, 
                   fontweight='heavy', color='navy',
                   family='serif', loc='left')
        ax_deselectALL = fig.add_axes([0.06, 0.01, 0.15, 0.07])
        ax_exit = fig.add_axes([0.004, 0.01, 0.05, 0.07])
        ax_continue = fig.add_axes([0.86, 0.01, 0.13, 0.07])
        
        scatter = ax.scatter(xnums, df['Temperature'], s=10, c=colors_initial, picker=5, zorder=1)
        ax.set_title(f"[{idx}/{len(mtr_files)}] Time Series Data- {mtr_file}")
        ax.set_xlabel("Date Time")
        ax.set_ylabel("Temperature")
        ax.grid(True)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

        btn_deselectALL = Button(ax_deselectALL, "Undo All Selections")
        btn_deselectALL.color = "lightblue"
        btn_deselectALL.hovercolor = "yellow"
        btn_deselectALL.label.set_fontsize(10)

        btn_exit = Button(ax_exit, "Exit")
        btn_exit.color = "salmon"
        btn_exit.hovercolor = "red"
        btn_exit.label.set_fontsize(10)

        btn_continue = Button(ax_continue, "Continue Next >>")
        btn_continue.color = "lightgreen"
        btn_continue.hovercolor = "limegreen"
        btn_continue.label.set_fontsize(10)
        
        radio_labels = [f"{k}: {FLAG_LABELS[k]}" for k in FLAG_LABELS]
        radio = RadioButtons(radio_ax, radio_labels, active=list(FLAG_LABELS.keys()).index(current_flag))

        for i, text in enumerate(radio.labels):
            flag = list(FLAG_LABELS.keys())[i]
            text.set_color(FLAG_COLORS[flag])
            x, y = text.get_position()
            # Small color square beside text
            rect = Rectangle((0.01, y - 0.017), 0.07, 0.05,
                            color=FLAG_COLORS[flag], transform=radio_ax.transAxes)
            radio_ax.add_patch(rect)
            text.set_family('serif')
            text.set_fontsize(10)
            text.set_weight('bold')
            text.set_linespacing(1)

        def set_current_flag_from_label(label):
            nonlocal current_flag
            current_flag = int(label.split(":")[0])
            logger.info(f"Current flag set to {current_flag}")
        
        def click_continue(event):
            nonlocal applied
            applied = True
            logger.info("Figure: Continue clicked.")
            plt.close(fig)  # close figure and continue
        
        def click_exit(event):
            nonlocal user_exited
            global exit_requested
            user_exited = True
            exit_requested = True
            logger.info("Figure: Exit clicked (exit_requested set True).")
            plt.close(fig)  # close figure and stop

        def onselect(verts):
            path = Path(verts)
            selected_indices = np.nonzero(path.contains_points(xy))[0].astype(int)
            if selected_indices.size == 0:
                return
            logger.info(f"Selected {len(selected_indices)} point(s) via LASSO using current flag: {current_flag}")
            df.iloc[selected_indices, df.columns.get_loc('qualityflag')] = current_flag
            try:
                facecolors = scatter.get_facecolors()
                new_rgba = np.array(mcolors.to_rgba(FLAG_COLORS[current_flag]))
                facecolors[selected_indices] = new_rgba
                scatter.set_facecolors(facecolors)
            except Exception:
                colors = [FLAG_COLORS[int(f)] for f in df['qualityflag']]
                scatter.set_color(colors)

            selected_dt = df.index[selected_indices]
            selected_temp = df['Temperature'].iloc[selected_indices].to_numpy()
            #Store selected points
            selected_df = pd.DataFrame({
                'DateTime': selected_dt, 
                'Temperature': selected_temp, 
                'idx': selected_indices,
                "Flag": current_flag })
            selection_groups.append(selected_df)
            fig.canvas.draw_idle()
            
        def click_deselect_all(event):
            nonlocal selection_groups, df, scatter
            selection_groups.clear()
            logger.info("Figure: Undo Selection clicked (all selections cleared).")
            df['qualityflag'] = qflag.copy()
            try:
                facecolors = scatter.get_facecolors()
                if facecolors.shape[0] != N:
                    colors = np.array([mcolors.to_rgba(FLAG_COLORS[int(f)]) for f in df["qualityflag"]])
                    ax.cla()
                    scatter = ax.scatter(xnums, df["Temperature"], s=12, c=colors, picker=5, zorder=2)
                    ax.set_title(f"[{idx}/{len(mtr_files)}] Time Series Data- {mtr_file}")
                    ax.set_xlabel("Date Time"); ax.set_ylabel("Temperature"); ax.grid(True)
                else:
                    new_rgba = np.array([mcolors.to_rgba(FLAG_COLORS[int(f)]) for f in df["qualityflag"]])
                    facecolors[:, :] = new_rgba
                    scatter.set_facecolors(facecolors)
            except Exception:
                colors = [FLAG_COLORS[int(f)] for f in df["qualityflag"]]
                scatter.set_color(colors)
            fig.canvas.draw_idle()
            logging.getLogger("qc_tool").info("Undo All Selections: restored original flags/colors.")


            # # Remove all artists from axes (clean reset)
            # ax.cla()

            # # Replot using initial colors
            # colors_initial = [FLAG_COLORS.get(f, "#808080") for f in df['qualityflag']]
            # scatter = ax.scatter(df.index, df['Temperature'], s=10, c=colors_initial,
            #                     picker=5, zorder=1)

            # # Restore axes labels, title, grid
            # ax.set_title(f"[{idx}/{len(mtr_files)}] Time Series Data- {mtr_file}")
            # ax.set_xlabel("Date Time")
            # ax.set_ylabel("Temperature")
            # ax.grid(True)
            # fig.canvas.draw_idle()
        
        def on_pick(event):
            # click-to-select: event.ind are positional indices
            if event.artist != scatter:
                return
            inds = np.unique(event.ind).astype(int)
            if inds.size == 0:
                return
            logger.info(f"Selected {len(inds)} point(s) via LASSO using current flag: {current_flag}")
            # apply current flag to df (positional)
            df.iloc[inds, df.columns.get_loc("qualityflag")] = current_flag
            # update only those facecolors
            try:
                facecolors = scatter.get_facecolors()
                new_rgba = np.array(mcolors.to_rgba(FLAG_COLORS[current_flag]))
                facecolors[inds] = new_rgba
                scatter.set_facecolors(facecolors)
            except Exception:
                colors = [FLAG_COLORS[int(f)] for f in df["qualityflag"]]
                scatter.set_color(colors)
            # record selection group
            sel_dt = df.index[inds]
            sel_temp = df["Temperature"].iloc[inds].to_numpy()
            sel_df = pd.DataFrame({"DateTime": sel_dt, "Temperature": sel_temp, "idx": inds, "Flag": current_flag})
            selection_groups.append(sel_df)
            fig.canvas.draw_idle()
            
        radio.on_clicked(set_current_flag_from_label)
        btn_continue.on_clicked(click_continue)
        btn_exit.on_clicked(click_exit)
        btn_deselectALL.on_clicked(click_deselect_all)
        lasso = LassoSelector(ax, onselect)
        cid = fig.canvas.mpl_connect("pick_event", on_pick)
        
        ## Plt show non-blocking
        plt.show(block=False)
        logger.info(
                    "QC Point Selection Tips:\n"
                    "- Use the Lasso tool (click and drag) to select multiple data points.\n"
                    "- Single points can also be selected using a mouse click.\n"
                    "- Choose the desired quality flag using the radio buttons BEFORE selecting points.\n"
                    "- Only select points that appear problematic or questionable.\n"
                    "- Focus primarily on flags:\n"
                    "    2: Inconsistent\n"
                    "    3: Doubtful\n"
                    "    4: Erroneous\n"
                    "    5: Modified\n"
                    "- Points not selected will automatically be assigned flag 1 (Correct) when you click 'Continue Next >>'.\n"
                    "- Use 'Undo All Selections' to clear all current selections and start over.\n"
                    "- Click 'Continue Next >>' to apply flags and proceed to the next file.\n"
                    "- Click 'Exit' to stop the QC process immediately."
                    )
       
        # Wait until the figure is closed, processing Qt events so the main GUI remains responsive
        app = QApplication.instance()
        while plt.fignum_exists(fig.number) and not exit_requested:
            if app:
                app.processEvents()
            time.sleep(0.001)

        # After closing the plot and collecting all selection groups
        if applied:
            if selection_groups:
                combined_indices= np.unique(np.concatenate([g['idx'].to_numpy() for g in selection_groups])).astype(int)
            else:
                combined_indices = np.array([], dtype=int)
            logger.info(f"Total of {len(combined_indices)} unique points selected for flagging.")

            if len(orig_df) != len(df):
                raise ValueError(f"Size mismatch: orig_df has {len(orig_df)} rows, but df has {len(df)} rows.")
            
            if len(combined_indices) > 0:
                orig_df.iloc[combined_indices, orig_df.columns.get_loc("QTE90_01")] = df.iloc[combined_indices]["qualityflag"].to_numpy()
                if qc_mode_code_ == 0:
                # Initial QC Mode: everything not selected → flag = 1
                    non_sel_mask = ~np.isin(np.arange(len(orig_df)), combined_indices)
                    orig_df.loc[non_sel_mask, "QTE90_01"] = 1
                elif qc_mode_code_ == 1:
                    # Review-QC Mode: only selected points are changed, others remain as is
                    pass
        else:
            if qc_mode_code_ == 0:
                # Initial QC Mode: no points selected → all flag = 1
                orig_df['QTE90_01'] = 1
                logger.info("No points were selected for this file.")
            elif qc_mode_code_ == 1:
                # Review-QC Mode: no points selected → no changes made
                logger.info("No points were selected for this file; no changes made.")
        
        orig_df_afterQC = orig_df.copy()
        afterQC_flags = orig_df_afterQC["QTE90_01"].to_numpy().astype(int)
        beforeQC_flags = orig_df_stored['QTE90_01'].to_numpy().astype(int)
        changed_mask = (beforeQC_flags != afterQC_flags)
        changed_rows = orig_df_stored.loc[changed_mask, ["SYTM_01", "TE90_01", "QTE90_01"]]
        transitions = Counter(zip(beforeQC_flags, afterQC_flags))
        for (before, after), count in transitions.items():
            if before != after:
                logger.info(f"Flag Code: {before} to Flag Code: {after}: {count}")
        if changed_rows.empty:
            logger.info(f"No quality flag changes were made for {mtr_file}.")
        else:
            logger.info(f"Total QC flags changed for {mtr_file}: {len(changed_rows)}")

        try:
            mtr.data.data_frame = orig_df
            mtr.add_history()
            if qc_mode_code_ == 0:
                mtr.add_to_history(f'APPLIED QUALITY CODE FLAGGING AND PERFORMED INITIAL VISUAL QC BY {qc_operator.upper()}')
            elif qc_mode_code_ == 1:
                mtr.add_to_history(f'REVIEWED AND UPDATED QUALITY CODE FLAGGING BY {qc_operator.upper()}')
            mtr.update_odf()
            file_spec = mtr.generate_file_spec()
            mtr.file_specification = file_spec
            logger.info(f"Writing file {idx} of {len(mtr_files)}: {mtr_file}")
            logger.info(f"Please wait...writing QC ODF file...")
            out_file = pathlib.Path(out_odf_path) / f"{file_spec}.ODF"
            mtr.write_odf(str(out_file), version=2.0)
            logger.info(f"QC completed for [{idx}/{len(mtr_files)}]: {mtr_file}")
            logger.info(f"Saved [{idx}/{len(mtr_files)}]: {out_file}")
        except Exception as e:
            logger.exception(f"Failed writing QC ODF for {mtr_file}: {e}")

    # Completed loop
    if not exit_requested and (idx == len(mtr_files)):
        logger.info(f"QC process completed for all {len(mtr_files)} files.")
        batch_result_container["finished"] = True
    elif exit_requested:
        logger.info(f"QC process was interrupted before completion ({idx} of {len(mtr_files)} files).")
        batch_result_container["finished"] = False
    else:
        # fallback
        batch_result_container["finished"] = False

    return batch_result_container


def main_select_inputs():
    app = QApplication.instance()
    must_quit_app = app is None
    if must_quit_app:
        app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    select_inputs = select_metadata_file_and_data_folder.SubWindowOne()
    select_inputs.show()

    result_container = {"finished": False, "input": None, "output": None, "operator": None}

    
    def on_accept():
        operator = select_inputs.qc_name.strip()
        input_path = select_inputs.input_data_folder
        output_path = select_inputs.output_data_folder

        if not operator or not input_path or not output_path:
            print("❌ Missing required fields.")
            return

        result_container["operator"] = operator
        result_container["input"] = input_path
        result_container["output"] = output_path
        result_container["finished"] = True
        select_inputs.close()

    def on_reject():
        print("❌ QC cancelled by user.")
        result_container["finished"] = False
        select_inputs.close()

    select_inputs.buttonBox.accepted.connect(on_accept)
    select_inputs.buttonBox.rejected.connect(on_reject)

    while select_inputs.isVisible():
        app.processEvents()
        time.sleep(0.05)

    if must_quit_app:
        pass

    if result_container["finished"]:
        return (
            result_container["input"],
            result_container["output"],
            result_container["operator"],
        )
    else:
        return None, None, None


def exit_program(app):
    """
    Clean exit.
    """
    global exit_requested
    exit_requested = True
    logger.info("Exit Program clicked — setting exit_requested and quitting.")
    # Allow logger to flush
    handlers = logger.handlers[:]
    for h in handlers:
        try:
            h.flush()
        except Exception:
            pass
    app.quit()


def start_qc_process(log_ui: LogWindowUI):
    """
    Called when Start QC button is clicked.
    It opens the metadata/input selection dialog, and if accepted, runs the QC workflow.
    """
    global exit_requested
    exit_requested = False
    logger.info("Start QC button clicked.")
    input_path, output_path, operator = main_select_inputs()
    if not input_path or not output_path or not operator:
        logger.info("QC start aborted: missing input, output, or operator.")
        return
    logger.info(
                "QC Inputs Selected:\n"
                f"  • QC Operator : {operator.strip().title()}\n"
                f"  • Input Path  : {input_path}\n"
                f"  • Output Path : {output_path}"
            )
    run_qc_thermograph_data(input_path, output_path, operator)
    logger.info("Finished batch successfully (returned to GUI).")
    logger.info("Please Start QC for new batch.")


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setStyle("Fusion")

    log_window = LogWindowUI()
    log_window.show()
    logger.addHandler(log_window.qtext_handler)
    logger.info("Log window initialized.")

    # Connect buttons
    log_window.btn_start.clicked.connect(lambda: start_qc_process(log_window))
    log_window.btn_exit.clicked.connect(lambda: exit_program(app))
    logger.info("Application started. Use Start QC to begin.")

    # Start the Qt event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
    
















