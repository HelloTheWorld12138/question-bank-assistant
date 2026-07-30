# MathType 结构化转换组件

此目录保存题库助手读取 Microsoft Equation Editor 3.0 与旧版 MathType/OLE 公式所需的固定版本组件。

运行链路：

1. 从 DOCX 中定位 `Equation.DSMT4`、`Equation.3` 等公式对象；
2. 读取 OLE 内的 MTEF 数据；
3. 使用 `mathtype_to_mathml_plus` 转换为 MathML；
4. 再由项目已有的 Pandoc 转换成 LaTeX 和 Word 原生公式。

固定依赖：

- `mathtype_to_mathml_plus` 0.0.16，MIT；
- `bindata` 2.4.15，BSD-2-Clause；
- `ruby-ole` 1.2.13.1，MIT。

基础程序不会联网下载这些文件。当前开发环境使用系统 Ruby；制作 Windows
发行包时应随应用提供固定 Ruby 运行时和 Nokogiri，不要求教师自行安装。

原始项目和许可证：

- https://rubygems.org/gems/mathtype_to_mathml_plus
- https://rubygems.org/gems/bindata
- https://rubygems.org/gems/ruby-ole

文件校验值（SHA-256）：

- `bindata-2.4.15.gem`：`e567e4278223e041caf4e623de870b2df8a93479d8f13e2b478bad45e0fbc413`
- `mathtype_to_mathml_plus-0.0.16.gem`：`d2d3b9d507b8bd19424f6a5dd1425aa0e27d27a55b695b127b18f01a463b0064`
- `ruby-ole-1.2.13.1.gem`：`578d10dd2a797a2b35a1286c6fb2c9525f67c24791346fc8015d39f0ffa3cb72`
