# NDI® SDK notice and terms

NDI® is a registered trademark of Vizrt NDI AB. Learn more about NDI at <https://ndi.video/>.

Patchbay is an independent product. It is **not** a product of Vizrt NDI AB, and it is
not affiliated with, sponsored or endorsed by Vizrt NDI AB. The name "NDI" is used only
to state that Patchbay is compatible with NDI.

## The NDI SDK is not included

Patchbay talks to the NDI runtime library (`libndi.so.6`) from the **NDI SDK**, which is
owned by Vizrt NDI AB (Copyright © Vizrt NDI AB, formerly NDI, Inc. All rights reserved).
This repository does **not** contain or redistribute any part of the NDI SDK: no
libraries, header files, documentation, logos or tools. Patchbay's own source code loads
the library at runtime.

To run Patchbay you must download the NDI SDK yourself from
<https://ndi.video/for-developers/ndi-sdk/> and accept Vizrt NDI AB's NDI SDK License
Agreement (<http://ndi.link/ndisdk_license>). Your use of the NDI SDK and runtime is
governed by that agreement, not by Patchbay's license. NDI tools (for example NDI Studio
Monitor and NDI Access Manager) are available from <https://ndi.video/tools/> and are not
distributed with Patchbay.

## Terms for the NDI components

These terms are required by section 3(d) of the NDI SDK License Agreement. They apply to
anyone who uses or distributes Patchbay together with the NDI SDK or runtime, in addition
to Patchbay's own license ([LICENSE](LICENSE)). If you redistribute Patchbay, or build
products on it that use the NDI SDK, you must pass these terms on to your recipients and
users.

1. **No modification.** You may not modify the NDI SDK, any specific NDI SDK, the NDI
   Products, or any part of them.
2. **No reverse engineering.** You may not reverse engineer, disassemble or recompile
   the NDI SDK, any specific NDI SDK or the NDI Products, or any part of them, or any
   protocols they use, whether transmitted or received over a network or used inside or
   outside the machine (physical or virtual) they run on. You may not attempt to do so.
3. **No circumvention.** You may not circumvent any technical limitations in the NDI
   SDK, any specific NDI SDK, the NDI Products, or any part of them.
4. **Notices.** You may not remove, obscure or alter any proprietary notices or labels
   contained on or within the NDI SDK, any specific NDI SDK, the NDI Products, or any part
   of them.
5. **No warranty from NDI.** Vizrt NDI AB and each of its licensors disclaim any and all
   warranties for the NDI SDK and runtime, express or implied.
6. **No liability of NDI.** To the extent permitted by applicable law, Vizrt NDI AB and
   its licensors are not liable for any damages, whether direct, indirect, incidental or
   consequential, arising from the use of Patchbay or any product that bundles it.
7. **Export control.** You must comply with all relevant export laws and regulations of
   the United States, and you may not export or re-export Patchbay or the NDI SDK, directly
   or indirectly, in violation of them.
8. **Copyright.** The NDI SDK and runtime are copyright Vizrt NDI AB (formerly NDI, Inc.).
9. **Downstream developers.** If you develop third-party products using Patchbay, you
   must comply with the terms of the NDI SDK License Agreement, including keeping current
   and complete NDI compatibility, and you must include the terms of this section in your
   own end-user license agreement.

## Deployment restrictions from Vizrt

The NDI SDK License Agreement (section 1(b)) covers software running on general-purpose
computers where the end user can freely change the operating system and install software.
It **excludes** deployment on:

- fixed-purpose physical appliances with a locked or restricted operating system,
- fixed-purpose virtual or cloud environments (including SaaS/PaaS) that materially
  restrict the user from changing the OS or installing software, and
- embedded devices.

For those uses you need a commercial license from Vizrt NDI AB (<https://ndi.video/>),
in addition to any license for Patchbay itself. A commercial license for Patchbay
([COMMERCIAL.md](COMMERCIAL.md)) does **not** include any rights to the NDI SDK.

## Trademark use in this project

In line with the NDI SDK documentation and the NDI brand guidelines:

- "NDI" appears with ® at its first use in each document, together with the statement
  "NDI® is a registered trademark of Vizrt NDI AB", and links to <https://ndi.video/>.
- The web UI shows the trademark statement and a link to <https://ndi.video/> next to the
  NDI source list, in the footer, on the login screen and in **⚙ Settings → About**.
- No NDI logos or brand assets are included.
- Patchbay's product name does not contain "NDI".

If you fork or redistribute Patchbay, keep these attributions and do not put "NDI" in the
name of your product without reading the NDI brand guidelines or contacting Vizrt NDI AB.
