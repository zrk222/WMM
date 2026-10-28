"""Deterministically create native app and XCTest targets without XcodeGen."""
from pathlib import Path
import hashlib,json,uuid

IOS=Path(__file__).resolve().parents[1]
objects={}
def key(name):return hashlib.sha256(name.encode()).hexdigest()[:24].upper()
def obj(label,isa,**fields):
    identity=key(label);objects[identity]=dict(isa=isa,**fields);return identity
def ref(path,kind,tree='<group>'):
    return obj(path,'PBXFileReference',path=path,lastKnownFileType=kind,sourceTree=tree)
def build(name,file,**extra):return obj(name,'PBXBuildFile',fileRef=file,**extra)
sources=['WMM/WMMApp.swift','WMM/Identity/KeychainVault.swift','WMM/Identity/LocalIdentity.swift','WMM/Identity/NativeSessionAuthority.swift','WMM/Bridge/DomainBridge.swift','WMM/Storage/LocalStore.swift','WMM/Bridge/EngineBootstrap.m','WMM/Media/TimelineRenderer.swift','WMM/Media/MediaInspector.swift','WMM/Media/MediaIntake.swift','WMM/Reports/ReportExport.swift']
types=lambda p:'sourcecode.c.objc' if p.endswith('.m') else 'sourcecode.swift'
files=[ref(p,types(p)) for p in sources]
testfile=ref('WMMTests/StorageIdentityTests.swift','sourcecode.swift')
intaketest=ref('WMMTests/ProviderIntakeTests.swift','sourcecode.swift')
mediatest=ref('WMMTests/MediaConformanceTests.swift','sourcecode.swift')
enginetest=ref('WMMTests/EngineBootstrapTests.swift','sourcecode.swift')
bridgetest=ref('WMMTests/BridgeAgentTests.swift','sourcecode.swift')
framework=ref('Python.xcframework','wrapper.xcframework')
app=obj('product-app','PBXFileReference',explicitFileType='wrapper.application',path='WMM.app',sourceTree='BUILT_PRODUCTS_DIR')
test=obj('product-tests','PBXFileReference',explicitFileType='wrapper.cfbundle',path='WMMTests.xctest',sourceTree='BUILT_PRODUCTS_DIR')
products=obj('products','PBXGroup',children=[app,test],name='Products',sourceTree='<group>')
group=obj('main','PBXGroup',children=files+[testfile,intaketest,mediatest,enginetest,bridgetest,framework,products],sourceTree='<group>')
sourcephase=obj('app-sources','PBXSourcesBuildPhase',buildActionMask=2147483647,files=[build('build-'+p,f) for p,f in zip(sources,files)],runOnlyForDeploymentPostprocessing=0)
testphase=obj('test-sources','PBXSourcesBuildPhase',buildActionMask=2147483647,files=[build('build-test',testfile),build('build-intake-test',intaketest),build('build-media-test',mediatest),build('build-engine-test',enginetest),build('build-bridge-test',bridgetest)],runOnlyForDeploymentPostprocessing=0)
link=obj('frameworks','PBXFrameworksBuildPhase',buildActionMask=2147483647,files=[build('link-python',framework)],runOnlyForDeploymentPostprocessing=0)
resources=obj('resources','PBXResourcesBuildPhase',buildActionMask=2147483647,files=[],runOnlyForDeploymentPostprocessing=0)
runtime=obj('runtime','PBXShellScriptBuildPhase',buildActionMask=2147483647,files=[],inputPaths=[],outputPaths=[],runOnlyForDeploymentPostprocessing=0,shellPath='/bin/bash',shellScript='bash "$PROJECT_DIR/Build/package_runtime.sh"',alwaysOutOfDate=1)
embed=obj('embed','PBXCopyFilesBuildPhase',buildActionMask=2147483647,dstPath='',dstSubfolderSpec=10,files=[build('embed-python',framework,settings={'ATTRIBUTES':['CodeSignOnCopy','RemoveHeadersOnCopy']})],runOnlyForDeploymentPostprocessing=0)
def configs(name,base):
    values=[]
    for mode in ['Debug','Release']:
        settings=dict(base,SWIFT_OPTIMIZATION_LEVEL='-Onone' if mode=='Debug' else '-O')
        values.append(obj(name+mode,'XCBuildConfiguration',name=mode,buildSettings=settings))
    return obj(name+'configs','XCConfigurationList',buildConfigurations=values,defaultConfigurationIsVisible=0,defaultConfigurationName='Release')
common={'IPHONEOS_DEPLOYMENT_TARGET':'17.0','SWIFT_VERSION':'5.0','SDKROOT':'iphoneos','TARGETED_DEVICE_FAMILY':'1,2','CODE_SIGN_STYLE':'Automatic','GENERATE_INFOPLIST_FILE':'YES','ENABLE_USER_SCRIPT_SANDBOXING':'NO','CLANG_ENABLE_MODULES':'YES','CLANG_ENABLE_OBJC_ARC':'YES'}
ac=configs('app',dict(common,PRODUCT_BUNDLE_IDENTIFIER='com.wizemarketingmachine.app',PRODUCT_NAME='$(TARGET_NAME)',SWIFT_OBJC_BRIDGING_HEADER='WMM/WMM-Bridging-Header.h',FRAMEWORK_SEARCH_PATHS=['$(inherited)','$(PROJECT_DIR)'],HEADER_SEARCH_PATHS=['$(BUILT_PRODUCTS_DIR)/Python.framework/Headers'],LD_RUNPATH_SEARCH_PATHS=['$(inherited)','@executable_path/Frameworks'],ENABLE_TESTABILITY='YES',INFOPLIST_KEY_UIApplicationSceneManifest_Generation='YES',INFOPLIST_KEY_UILaunchScreen_Generation='YES'))
tc=configs('tests',dict(common,PRODUCT_BUNDLE_IDENTIFIER='com.wizemarketingmachine.tests',PRODUCT_NAME='$(TARGET_NAME)',TEST_HOST='$(BUILT_PRODUCTS_DIR)/WMM.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/WMM',BUNDLE_LOADER='$(TEST_HOST)'))
target=obj('app-target','PBXNativeTarget',name='WMM',buildConfigurationList=ac,buildPhases=[sourcephase,link,resources,runtime,embed],buildRules=[],dependencies=[],productName='WMM',productReference=app,productType='com.apple.product-type.application')
proxy=obj('test-proxy','PBXContainerItemProxy',containerPortal=key('project'),proxyType=1,remoteGlobalIDString=target,remoteInfo='WMM')
dependency=obj('test-dependency','PBXTargetDependency',target=target,targetProxy=proxy)
tests=obj('test-target','PBXNativeTarget',name='WMMTests',buildConfigurationList=tc,buildPhases=[testphase],buildRules=[],dependencies=[dependency],productName='WMMTests',productReference=test,productType='com.apple.product-type.bundle.unit-test')
pc=configs('project',common)
project=obj('project','PBXProject',attributes={'LastUpgradeCheck':'1600'},buildConfigurationList=pc,compatibilityVersion='Xcode 14.0',developmentRegion='en',hasScannedForEncodings=0,knownRegions=['en','Base'],mainGroup=group,productRefGroup=products,projectDirPath='',projectRoot='',targets=[target,tests])
def encode(value):
    if isinstance(value,dict):return '{\n'+''.join(f'{json.dumps(k)} = {encode(v)};\n' for k,v in value.items())+'}'
    if isinstance(value,list):return '('+','.join(encode(v) for v in value)+')'
    if isinstance(value,int):return str(value)
    return json.dumps(value)
folder=IOS/'WMM.xcodeproj';folder.mkdir(exist_ok=True)
(folder/'project.pbxproj').write_text('// !$*UTF8*$!\n'+encode({'archiveVersion':1,'classes':{},'objectVersion':56,'objects':objects,'rootObject':project})+'\n',encoding='utf-8')
shared=folder/'xcshareddata/xcschemes';shared.mkdir(parents=True,exist_ok=True)
def entry(identity,name):return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{identity}" BuildableName="{name}" BlueprintName="{name.split(".")[0]}" ReferencedContainer="container:WMM.xcodeproj"/>'
(shared/'WMM.xcscheme').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1600" version="1.3"><BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{entry(target,'WMM.app')}</BuildActionEntry></BuildActionEntries></BuildAction><TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB"><Testables><TestableReference skipped="NO">{entry(tests,'WMMTests.xctest')}</TestableReference></Testables></TestAction><LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{entry(target,'WMM.app')}</BuildableProductRunnable></LaunchAction><ProfileAction buildConfiguration="Release"/><AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/></Scheme>
''',encoding='utf-8')
plans=folder/'xcshareddata/xctestplans';plans.mkdir(parents=True,exist_ok=True)
for name in ('WMMCoreContract','WMMDeviceAcceptance'):
    plan={'version':1,'configurations':[{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'wmm/test-plan/'+name)),'name':name,'options':{}}],
          'defaultOptions':{},'testTargets':[{'parallelizable':False,'target':{
              'containerPath':'container:WMM.xcodeproj','identifier':tests,'name':'WMMTests'}}]}
    (plans/(name+'.xctestplan')).write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
scheme=shared/'WMM.xcscheme'
body=scheme.read_text(encoding='utf-8')
body=body.replace('<Testables>', '<TestPlans><TestPlanReference reference="container:WMM.xcodeproj/xcshareddata/xctestplans/WMMCoreContract.xctestplan" default="YES"/><TestPlanReference reference="container:WMM.xcodeproj/xcshareddata/xctestplans/WMMDeviceAcceptance.xctestplan"/></TestPlans><Testables>')
scheme.write_text(body,encoding='utf-8')
print('Generated WMM app and XCTest project; native build remains NOT_RUN')
