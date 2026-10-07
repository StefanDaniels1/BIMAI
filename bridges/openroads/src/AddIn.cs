using System;

namespace Bimai.OpenRoads
{
    /// <summary>
    /// The add-in OpenRoads Designer loads (MS_DGNAPPS, or the key-in `mdl load BimaiOpenRoads`). The only
    /// file that compiles against Bentley's assemblies: a class inheriting Bentley.MstnPlatformNET.AddIn with
    /// an MdlTaskID, a constructor taking the MDL descriptor, and Run (OpenRoads Designer SDK: "Developing
    /// with the Managed SDK"). Run is called on OpenRoads' main thread, so the dispatcher is created here.
    /// </summary>
    [Bentley.MstnPlatformNET.AddInAttribute(MdlTaskID = "BIMAIBRIDGE")]
    public sealed class BridgeAddIn : Bentley.MstnPlatformNET.AddIn
    {
        private static MainThreadDispatcher _dispatcher;

        private BridgeAddIn(IntPtr mdlDesc) : base(mdlDesc)
        {
        }

        protected override int Run(string[] commandLine)
        {
            var log = new Log(Log.DefaultPath());
            try
            {
                if (Bridge.Current != null && Bridge.Current.Server != null && Bridge.Current.Server.IsRunning) return 0;
                _dispatcher = new MainThreadDispatcher(TimeSpan.FromSeconds(30));
                Bridge.Start(_dispatcher, CivilTools.Create(_dispatcher), log, Bridge.ReadPort());
            }
            catch (Exception ex)
            {
                log.Error("bridge did not load", ex);
            }
            return 0;
        }
    }
}
