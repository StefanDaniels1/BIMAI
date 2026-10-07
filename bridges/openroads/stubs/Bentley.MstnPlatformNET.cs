// Stand-in for Bentley's Bentley.MstnPlatformNET.dll, ONLY for compiling the bridge in CI (bimai's tests).
// It declares the few members AddIn.cs uses, with the shapes from Bentley's OpenRoads Designer SDK
// documentation. On a real PC bimai compiles against the installed OpenRoads Designer instead.
using System;

namespace Bentley.MstnPlatformNET
{
    [AttributeUsage(AttributeTargets.Class)]
    public sealed class AddInAttribute : Attribute
    {
        public string MdlTaskID { get; set; }
    }

    public abstract class AddIn
    {
        protected AddIn(IntPtr mdlDesc) { }
        protected abstract int Run(string[] commandLine);
    }
}
